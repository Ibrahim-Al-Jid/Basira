"""GitHub App authorization and snapshots as the signed-in Basira account."""

import base64
from datetime import timedelta
from hashlib import sha256
import hmac
import json
import logging
import os
from pathlib import Path
import re
from secrets import token_urlsafe
from urllib.parse import quote, urlencode
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import delete, select

from . import github_import as github
from .identity import require_session_user, session_digest
from .personal_projects import personal_user
from .platform_db import PersonalGitHubGrant, PersonalGitHubState, User, bind_owner, personal_projects_enabled, platform_session
from .platform_runtime import now

router = APIRouter(prefix="/api/platform/github", tags=["Personal GitHub"])
OAUTH = "https://github.com/login/oauth"
CALLBACK_PATH = "/api/platform/github/callback"
CALLBACK_COOKIE = "basira_github_callback"
CALLBACK_TTL = 600
MAX_PAGES = 5


class HideCallbackQuery(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            peer, method, path, version, status = record.args
            if isinstance(path, str) and path.split("?", 1)[0] == CALLBACK_PATH:
                record.args = peer, method, CALLBACK_PATH, version, status
        return True


logging.getLogger("uvicorn.access").addFilter(HideCallbackQuery())


def config():
    local = local_config()
    client_id = os.getenv("BASIRA_GITHUB_CLIENT_ID") or local.get("client_id", "")
    secret = os.getenv("BASIRA_GITHUB_CLIENT_SECRET") or local.get("client_secret", "")
    callback = os.getenv("BASIRA_GITHUB_CALLBACK_URL") or local.get("callback_url", "")
    key = os.getenv("BASIRA_GITHUB_CREDENTIAL_KEY") or local.get("credential_key", "")
    if not client_id or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", client_id) or not secret or not re.fullmatch(
        r"(?:https://[A-Za-z0-9.-]+(?::[0-9]+)?|http://127\.0\.0\.1:[0-9]+)" + CALLBACK_PATH, callback
    ):
        return None
    try:
        return client_id, secret, callback, Fernet(key.encode("ascii"))
    except (ValueError, UnicodeError):
        return None


def local_config():
    path = Path(__file__).resolve().parents[1] / "data" / "windows-local" / "provider-vault" / "github-app.json"
    try:
        with path.open(encoding="utf-8") as file:
            settings = json.loads(file.read(8192))
    except (OSError, ValueError):
        return {}
    if isinstance(settings, dict) and all(isinstance(value, str) for value in settings.values()):
        return settings
    return {}


def settings():
    result = config()
    if not result:
        raise HTTPException(503, "GitHub App محتاج إعداد على الخادم.")
    return result


def serialize_account(db, user_id):
    bind_owner(db, user_id)
    db.execute(select(User.id).where(User.id == user_id).with_for_update())


@router.post("/authorize")
def authorize(request: Request):
    user = personal_user(request)
    client_id, _, callback, cipher = settings()
    if callback != str(request.base_url).rstrip("/") + CALLBACK_PATH:
        raise HTTPException(409, "افتح بصيرة من العنوان المسجل في إعداد GitHub وحاول تاني.")
    digest = session_digest(request)
    state, verifier = token_urlsafe(32), token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).decode().rstrip("=")
    with platform_session() as db:
        serialize_account(db, user.id)
        db.execute(delete(PersonalGitHubState).where(PersonalGitHubState.user_id == user.id))
        db.add(PersonalGitHubState(user_id=user.id, state_digest=sha256(state.encode()).hexdigest(),
                                   session_digest=digest, ciphertext=cipher.encrypt(verifier.encode()),
                                   expires_at=now() + timedelta(seconds=CALLBACK_TTL)))
    response = JSONResponse({"url": OAUTH + "/authorize?" + urlencode({
        "client_id": client_id, "redirect_uri": callback, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256", "scope": "offline_access",
    })})
    # A top-level GET from GitHub cannot carry the Strict platform cookie.
    response.set_cookie(CALLBACK_COOKIE, cipher.encrypt(("github:" + digest).encode()).decode(),
                        max_age=CALLBACK_TTL, path=CALLBACK_PATH, secure=callback.startswith("https:"),
                        httponly=True, samesite="lax")
    return response


def token_identity(client_id, secret, callback, code, verifier):
    with github.client() as client:
        payload = github.provider_json(client.post(OAUTH + "/access_token", headers={"Accept": "application/json"},
            data={"client_id": client_id, "client_secret": secret, "redirect_uri": callback,
                  "code": code, "code_verifier": verifier}), 200)
        if payload.get("error") == "incorrect_client_credentials":
            raise github.GitHubFailure(424, "GitHub rejected the app credentials.")
        if payload.get("error"):
            raise github.GitHubFailure(409, "GitHub rejected the authorization exchange.")
        token, ttl = payload.get("access_token"), payload.get("expires_in")
        if (not isinstance(token, str) or not re.fullmatch(r"ghu_[A-Za-z0-9_]{10,250}", token)
                or type(ttl) is not int or not 0 < ttl <= 28_800):
            raise github.GitHubFailure(422, "فعّل انتهاء صلاحية توكنات GitHub App وأعد الربط.")
        who = github.provider_json(client.get(github.API + "/user", headers=github.headers(token)), 200)
        return token, ttl, str(provider_id(who.get("id")))


def callback_session(request, cipher):
    cookie = request.cookies.get(CALLBACK_COOKIE, "")
    if not cookie or len(cookie) > 512:
        raise HTTPException(403)
    try:
        proof = cipher.decrypt(cookie.encode("ascii"), ttl=CALLBACK_TTL)
    except (InvalidToken, UnicodeError):
        raise HTTPException(403) from None
    if not re.fullmatch(rb"github:[a-f0-9]{64}", proof):
        raise HTTPException(403)
    digest = proof.removeprefix(b"github:").decode("ascii")
    current = session_digest(request)
    if current and not hmac.compare_digest(current, digest):
        raise HTTPException(403)
    return digest


def consume_state(db, user_id, digest, state, cipher):
    serialize_account(db, user_id)
    entry = db.get(PersonalGitHubState, user_id)
    if (not entry or entry.expires_at.replace(tzinfo=None) <= now()
            or not hmac.compare_digest(entry.session_digest, digest)
            or not hmac.compare_digest(entry.state_digest, sha256(state.encode()).hexdigest())):
        raise HTTPException(403, "طلب ربط GitHub انتهت صلاحيته أو بدأ من جلسة مختلفة.")
    db.delete(entry)
    try:
        return cipher.decrypt(entry.ciphertext, ttl=CALLBACK_TTL).decode("ascii")
    except InvalidToken:
        raise HTTPException(403, "طلب ربط GitHub غير صالح.") from None


@router.get("/callback", include_in_schema=False)
def oauth_callback(request: Request, state: str = "", code: str = ""):
    destination = "/settings?tab=github&github=failed"
    consumed = False
    try:
        if not personal_projects_enabled():
            raise HTTPException(404)
        client_id, secret, callback, cipher = settings()
        if not state or len(state) > 128 or len(code) > 512:
            raise HTTPException(422)
        digest = callback_session(request, cipher)
        user = require_session_user(request, digest)
        # Hold the state transaction only during consume. A superseding connect or disconnect
        # invalidates the pending callback before it can persist the new grant.
        with platform_session() as db:
            verifier = consume_state(db, user.id, digest, state, cipher)
            if code:
                marker = sha256(("used:" + state).encode()).hexdigest()
                db.flush()
                db.add(PersonalGitHubState(user_id=user.id, state_digest=marker,
                    session_digest=digest, ciphertext=cipher.encrypt(b""),
                    expires_at=now() + timedelta(minutes=1)))
        consumed = True
        if code:
            try:
                token, ttl, identity = github.provider_call(token_identity, client_id, secret, callback, code, verifier)
            except HTTPException as error:
                if error.status_code == 424:
                    destination = "/settings?tab=github&github=credentials"
                elif error.status_code == 422:
                    destination = "/settings?tab=github&github=expiration"
                elif error.status_code == 502:
                    destination = "/settings?tab=github&github=unavailable"
                raise
            require_session_user(request, digest)
            with platform_session() as db:
                serialize_account(db, user.id)
                pending = db.get(PersonalGitHubState, user.id)
                if not pending or pending.state_digest != marker or pending.expires_at.replace(tzinfo=None) <= now():
                    raise HTTPException(409)
                db.delete(pending)
                db.merge(PersonalGitHubGrant(user_id=user.id, provider_user_id=identity, generation=uuid4().hex,
                                             ciphertext=cipher.encrypt(token.encode("ascii")),
                                             expires_at=now() + timedelta(seconds=ttl)))
            destination = "/settings?tab=github&github=connected"
    except HTTPException:
        pass
    response = RedirectResponse(destination, 303, headers={"Referrer-Policy": "no-referrer"})
    if consumed:
        response.delete_cookie(CALLBACK_COOKIE, path=CALLBACK_PATH, httponly=True, samesite="lax")
    return response


@router.delete("/connection", status_code=204)
def disconnect(request: Request):
    user = personal_user(request)
    try:
        generation, token = grant_for(user.id)
    except HTTPException:
        generation, token = None, None
    with platform_session() as db:
        serialize_account(db, user.id)
        db.execute(delete(PersonalGitHubState).where(PersonalGitHubState.user_id == user.id))
        grant = db.get(PersonalGitHubGrant, user.id, with_for_update=True)
        if grant:
            if generation != grant.generation:
                token = None
            db.delete(grant)
    if token:
        try:
            github.provider_call(revoke_token, token)
        except HTTPException:
            # The local grant is already deleted. GitHub also enforces token expiry.
            pass


def revoke_token(token):
    client_id, secret, _, _ = settings()
    with github.client() as client:
        client.request("DELETE", f"{github.API}/applications/{client_id}/token",
                       auth=httpx.BasicAuth(client_id, secret), json={"access_token": token},
                       headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": github.API_VERSION})


def grant_for(user_id):
    _, _, _, cipher = settings()
    with platform_session() as db:
        bind_owner(db, user_id)
        row = db.get(PersonalGitHubGrant, user_id)
        if row and row.expires_at.replace(tzinfo=None) <= now():
            db.execute(delete(PersonalGitHubGrant).where(
                PersonalGitHubGrant.user_id == user_id, PersonalGitHubGrant.generation == row.generation,
            ))
        elif row:
            try:
                return row.generation, cipher.decrypt(row.ciphertext, ttl=28_800).decode("ascii")
            except InvalidToken:
                pass
    raise HTTPException(409, "اربط حسابك بـGitHub من جديد.")


def connection_status(user_id):
    if not config():
        return {"connect_available": False, "connected": False}
    try:
        grant_for(user_id)
    except HTTPException:
        return {"connect_available": True, "connected": False}
    return {"connect_available": True, "connected": True}


@router.get("/connection")
def connection(request: Request):
    return connection_status(personal_user(request).id)


@router.get("/setup")
def setup(request: Request):
    personal_user(request)
    configured = config()
    callback = configured[2] if configured else str(request.base_url).rstrip("/") + CALLBACK_PATH
    slug = os.getenv("BASIRA_GITHUB_APP_SLUG") or local_config().get("slug", "")
    install = "https://github.com/apps/" + slug + "/installations/new" if re.fullmatch(r"[a-z0-9-]{1,100}", slug) else None
    return {"callback_url": callback, "install_url": install}


def provider_id(value):
    if type(value) is not int or not 0 < value <= github.MAX_INSTALLATION:
        raise ValueError("Invalid GitHub ID")
    return value


def pages(client, token, path, key):
    for page in range(1, MAX_PAGES + 1):
        response = client.get(github.API + path, headers=github.headers(token),
                              params={"per_page": 100, "page": page})
        items = github.provider_json(response, 200).get(key)
        if not isinstance(items, list) or len(items) > 100:
            raise ValueError("Invalid GitHub listing")
        yield from items
        if "next" not in response.links:
            return
    raise github.GitHubFailure(422, "قائمة GitHub أكبر من الحدود المسموحة. استخدم تثبيت بصلاحيات أقل.")


def available_installations(client, token):
    for installation in pages(client, token, "/user/installations", "installations"):
        if not isinstance(installation, dict):
            raise ValueError("Invalid GitHub installation")
        permissions = installation.get("permissions")
        if (installation.get("repository_selection") == "selected" and not installation.get("suspended_at")
                and isinstance(permissions, dict) and permissions.get("contents") == "read"
                and all(key in {"contents", "metadata"} and value == "read"
                        for key, value in permissions.items())):
            yield provider_id(installation.get("id"))


def repository_rows(client, token, installation_id):
    for row in pages(client, token, f"/user/installations/{installation_id}/repositories", "repositories"):
        if not isinstance(row, dict):
            raise ValueError("Invalid GitHub repository")
        name = row.get("full_name")
        permissions = row.get("permissions")
        if (isinstance(name, str) and re.fullmatch(github.OWNER_REPO, name)
                and name.split("/")[1] not in {".", ".."} and isinstance(permissions, dict)
                and permissions.get("pull") is True):
            yield {"installation_id": installation_id, "repository_id": provider_id(row.get("id")),
                   "repository": name, "default_branch": str(row.get("default_branch") or "")[:200],
                   "private": row.get("private") if type(row.get("private")) is bool else None}


def visible_repos(token):
    with github.client() as client:
        response = client.get(github.API + "/user", headers=github.headers(token))
        if response.status_code == 401:
            return None
        account = github.provider_json(response, 200)
        login = account.get("login")
        if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", login):
            raise ValueError("Invalid GitHub login")
        installations = list(available_installations(client, token))
        if len(installations) > 10:
            raise github.GitHubFailure(422, "عدد تثبيتات GitHub أكبر من الحد المسموح.")
        rows = [row for installation in installations for row in repository_rows(client, token, installation)]
        return login, rows


@router.get("/repositories")
def repositories(request: Request):
    user_id = personal_user(request).id
    generation, token = grant_for(user_id)
    result = github.provider_call(visible_repos, token)
    if result is None:
        with platform_session() as db:
            bind_owner(db, user_id)
            db.execute(delete(PersonalGitHubGrant).where(
                PersonalGitHubGrant.user_id == user_id, PersonalGitHubGrant.generation == generation,
            ))
        raise HTTPException(409, "اربط حسابك بـGitHub من جديد.")
    login, rows = result
    return {"account": {"login": login}, "repositories": [
        {**row, "installation_id": str(row["installation_id"]), "repository_id": str(row["repository_id"])}
        for row in rows
    ]}


def fetch_snapshot(token, installation_id, repository_id, ref):
    with github.client() as client:
        if installation_id in available_installations(client, token):
            for row in repository_rows(client, token, installation_id):
                if row["repository_id"] == repository_id:
                    repo = row["repository"]
                    is_sha = bool(re.fullmatch(github.SHA, ref))
                    endpoint = "commits" if is_sha else "branches"
                    response = client.get(f"{github.API}/repos/{repo}/{endpoint}/{quote(ref, safe='')}",
                                          headers=github.headers(token))
                    value = github.provider_json(response, 200)
                    commit_data = value if is_sha else value.get("commit")
                    commit = commit_data.get("sha") if isinstance(commit_data, dict) else None
                    if not isinstance(commit, str) or not re.fullmatch(r"[a-f0-9]{40}", commit):
                        raise ValueError("Invalid GitHub commit")
                    if is_sha and ref.lower() != commit:
                        raise github.GitHubFailure(409, "GitHub لم يؤكد النسخة المطلوبة.")
                    return row, commit, github.download_archive(client, token, repo, commit)
    raise github.GitHubFailure(409, "المستودع خارج صلاحيات GitHub الحالية.")
