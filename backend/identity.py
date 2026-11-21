"""OIDC sign-in, revocable sessions, and organization/project permissions."""

from dataclasses import dataclass
from datetime import UTC, timedelta
from functools import lru_cache
import hashlib
import os
import re
import secrets
from typing import Literal
import unicodedata
from urllib.parse import urlsplit

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from joserfc.errors import JoseError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

try:
    import httpx2 as oidc_httpx
except ImportError:
    import httpx as oidc_httpx

from .platform_db import (
    AuthSession, Membership, Organization, PlatformUnavailable, Project, ProjectGrant,
    User, platform_database_url, platform_session, utc_now,
)

router = APIRouter(prefix="/api/platform", tags=["Project identity"])
SESSION_COOKIE = "marsad_platform_session"
STATE_COOKIE = "marsad_oidc_state"
PASSWORD_ISSUER = "urn:marsad:password"
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
SESSION_TTL = timedelta(hours=8)
SESSION_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
MANAGERS = {"owner", "admin"}
READ = {"read", "export"}
ANALYZE = READ | {"scan", "finding"}
ROLE_ACTIONS = {
    "owner": ANALYZE | {"manage"},
    "admin": ANALYZE | {"manage"},
    "analyst": ANALYZE,
    "viewer": READ,
}
SIGNING_ALGORITHMS = {"RS256", "RS384", "RS512", "PS256", "ES256", "EdDSA"}


@dataclass(frozen=True)
class OIDCSettings:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str


@dataclass(frozen=True)
class ProjectContext:
    org_id: str
    project_id: str
    user_id: str
    role: str


class NamedResource(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Expected a visible name")
        return value


class MemberInput(BaseModel):
    user_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    role: Literal["admin", "analyst", "viewer"]


class GrantInput(BaseModel):
    user_id: str = Field(pattern=r"^[0-9a-f]{32}$")


def normalize_person_name(value):
    value = " ".join(part for part in unicodedata.normalize("NFC", value).split(" ") if part)
    if not 1 <= len(value) <= 80 or not any(char.isalpha() for char in value) or any(
        not (char in " .-'’" or unicodedata.category(char)[0] in {"L", "M"}) for char in value
    ):
        raise ValueError("Use a valid personal name")
    return value


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str = Field(max_length=80)
    last_name: str = Field(max_length=80)
    username: str | None = Field(default=None, max_length=30)

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_name(cls, value):
        return normalize_person_name(value)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._]{1,28}[a-zA-Z0-9]", value):
            raise ValueError("Use a username of 3–30 letters, digits, dots or underscores")
        return value.lower()


def public_name(name):
    return name if name and "@" not in name else ""


def member_name(name):
    return public_name(name) or "Marsad member"


def account_view(user):
    created = user.created_at
    return {"id": user.id, "display_name": public_name(user.display_name),
            "first_name": user.first_name, "last_name": user.last_name, "username": user.username,
            "created_at": created if created.tzinfo else created.replace(tzinfo=UTC)}


def member_view(row):
    return {**row, "display_name": member_name(row["display_name"])}


def endpoint_allowed(url):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return bool(parsed.hostname and parsed.username is None and parsed.password is None and not parsed.fragment and (
        parsed.scheme == "https" or
        (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"})
    ))


def oidc_settings():
    issuer = os.environ.get("MARSAD_OIDC_ISSUER", "")
    redirect_uri = os.environ.get("MARSAD_OIDC_REDIRECT_URI", "")
    client_id = os.environ.get("MARSAD_OIDC_CLIENT_ID", "")
    secret = os.environ.get("MARSAD_OIDC_CLIENT_SECRET", "")
    state_secret = os.environ.get("MARSAD_OIDC_STATE_SECRET", "")
    if (not endpoint_allowed(issuer) or len(issuer) > 500 or urlsplit(issuer).query or
            not endpoint_allowed(redirect_uri) or not client_id or not secret or len(state_secret) < 32):
        raise PlatformUnavailable("OIDC sign-in is not configured.")
    return OIDCSettings(issuer, client_id, secret, redirect_uri)


@lru_cache(maxsize=2)
def oauth_client(settings):
    oauth = OAuth()
    return oauth.register(
        "marsad_oidc", client_id=settings.client_id, client_secret=settings.client_secret,
        server_metadata_url=settings.issuer.rstrip("/") + "/.well-known/openid-configuration",
        client_kwargs={"scope": "openid profile", "code_challenge_method": "S256", "timeout": 10.0},
    )


async def checked_oauth(settings):
    client = oauth_client(settings)
    metadata = await client.load_server_metadata()
    endpoints = ("authorization_endpoint", "token_endpoint", "jwks_uri")
    if metadata.get("issuer") != settings.issuer or any(not endpoint_allowed(metadata.get(key)) for key in endpoints):
        raise ValueError("Invalid issuer metadata")
    algorithms = [name for name in metadata.get("id_token_signing_alg_values_supported", ["RS256"])
                  if name in SIGNING_ALGORITHMS]
    if not algorithms:
        raise ValueError("Unsupported identity token signature")
    metadata["id_token_signing_alg_values_supported"] = algorithms
    return client


def token_digest(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def session_digest(request):
    token = request.cookies.get(SESSION_COOKIE, "")
    return token_digest(token) if SESSION_TOKEN.fullmatch(token) else None


def issue_session(db, user_id, old_digest):
    now = utc_now()
    token = secrets.token_urlsafe(32)
    if old_digest:
        db.execute(update(AuthSession).where(
            AuthSession.token_digest == old_digest, AuthSession.revoked_at.is_(None),
        ).values(revoked_at=now))
    db.add(AuthSession(token_digest=token_digest(token), user_id=user_id,
                       created_at=now, expires_at=now + SESSION_TTL))
    return token


def set_platform_cookie(response, token, *, secure):
    response.set_cookie(SESSION_COOKIE, token, max_age=int(SESSION_TTL.total_seconds()),
                        secure=secure, httponly=True, samesite="strict")
    return response


def password_auth_enabled(request):
    return (
        os.environ.get("MARSAD_PASSWORD_AUTH_ENABLED") == "1"
        and bool(os.environ.get("MARSAD_PLATFORM_DATABASE_URL"))
        and request.url.hostname in LOCAL_HOSTS
    )


def require_user(request):
    digest = session_digest(request)
    if digest:
        with platform_session() as db:
            user = db.scalar(
                select(User).join(AuthSession, AuthSession.user_id == User.id).where(
                    AuthSession.token_digest == digest, AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > utc_now(), User.disabled_at.is_(None),
                )
            )
            if user and (user.issuer != PASSWORD_ISSUER or password_auth_enabled(request)):
                return user
    raise HTTPException(401, "سجّل الدخول للوصول للمشاريع.")


def require_membership(db, org_id, user_id):
    member = db.get(Membership, (org_id, user_id))
    if not member or member.revoked_at is not None:
        raise HTTPException(404, "المؤسسة غير متاحة.")
    return member


def project_access(db, project_id, user_id):
    return db.execute(
        select(Project.org_id, Membership.role).join(
            Membership, and_(Membership.org_id == Project.org_id, Membership.user_id == user_id,
                             Membership.revoked_at.is_(None)),
        ).join(User, and_(User.id == Membership.user_id, User.disabled_at.is_(None))).outerjoin(
            ProjectGrant, and_(
                ProjectGrant.org_id == Project.org_id, ProjectGrant.project_id == Project.id,
                ProjectGrant.user_id == user_id, ProjectGrant.revoked_at.is_(None),
            ),
        ).where(Project.id == project_id,
                or_(Membership.role.in_(MANAGERS), ProjectGrant.user_id.is_not(None)))
    ).one_or_none()


def require_project(request, project_id, action):
    user = require_user(request)
    with platform_session() as db:
        result = project_access(db, project_id, user.id)
    if not result:
        raise HTTPException(404, "المشروع غير متاح.")
    if action not in ROLE_ACTIONS[result.role]:
        raise HTTPException(403, "صلاحيتك لا تسمح بالإجراء ده.")
    return ProjectContext(result.org_id, project_id, user.id, result.role)


def persist_login(settings, claims, old_digest):
    subject = claims.get("sub")
    if not isinstance(subject, str) or not 1 <= len(subject) <= 255 or "\x00" in subject:
        raise ValueError("Missing verified subject")
    if claims.get("iss") != settings.issuer:
        raise ValueError("Unexpected identity issuer")
    audience = claims.get("aud")
    if isinstance(audience, str):
        audience = [audience]
    if audience != [settings.client_id]:
        raise ValueError("Unexpected identity audience")
    name = claims.get("name")
    display_name = name.replace("\x00", "").strip()[:200] if isinstance(name, str) else ""
    display_name = public_name(display_name)
    identity = select(User).where(User.issuer == settings.issuer, User.subject == subject)
    with platform_session() as db:
        user = db.scalar(identity)
        if user is None:
            try:
                with db.begin_nested():
                    user = User(issuer=settings.issuer, subject=subject, display_name=display_name)
                    db.add(user)
                    db.flush()
            except IntegrityError:
                user = db.scalar(identity)
                if user is None:
                    raise
        if user.disabled_at is not None:
            raise HTTPException(403, "الحساب غير متاح.")
        if not user.first_name:
            user.display_name = display_name
        return issue_session(db, user.id, old_digest)


@router.get("/auth/login")
async def login(request: Request):
    settings = oidc_settings()
    platform_database_url()
    try:
        client = await checked_oauth(settings)
        request.session["previous_session"] = session_digest(request)
        return await client.authorize_redirect(request, settings.redirect_uri)
    except (OAuthError, JoseError, oidc_httpx.HTTPError, ValueError, TypeError, KeyError):
        raise HTTPException(502, "تعذّر بدء تسجيل الدخول.") from None


@router.get("/auth/callback")
async def callback(request: Request):
    settings = oidc_settings()
    platform_database_url()
    try:
        client = await checked_oauth(settings)
        result = await client.authorize_access_token(request, leeway=30)
        claims = result.get("userinfo")
        if not result.get("id_token") or not claims:
            raise ValueError("Verified identity missing")
        token = await run_in_threadpool(persist_login, settings, claims, request.session.pop("previous_session", None))
    except (OAuthError, JoseError, oidc_httpx.HTTPError, ValueError, TypeError, KeyError):
        raise HTTPException(400, "تعذّر التحقق من تسجيل الدخول. ابدأ من جديد.") from None
    response = RedirectResponse("/dashboard", status_code=303, headers={"Referrer-Policy": "no-referrer"})
    return set_platform_cookie(response, token, secure=urlsplit(settings.redirect_uri).scheme == "https")


@router.get("/auth/me")
def me(request: Request):
    return account_view(require_user(request))


@router.put("/auth/profile")
def update_profile(body: ProfileInput, request: Request):
    actor = require_user(request)
    try:
        with platform_session() as db:
            user = db.scalar(select(User).where(User.id == actor.id, User.disabled_at.is_(None)).with_for_update())
            if not user:
                raise HTTPException(401, "الحساب غير متاح.")
            user.first_name, user.last_name, user.username = body.first_name, body.last_name, body.username
            user.display_name = f"{body.first_name} {body.last_name}"
            db.flush()
            updated = account_view(user)
    except IntegrityError:
        raise HTTPException(409, "اسم المستخدم مستخدم بالفعل.") from None
    return updated


@router.post("/auth/logout", status_code=204)
def logout(request: Request):
    digest = session_digest(request)
    if digest:
        with platform_session() as db:
            db.execute(update(AuthSession).where(
                AuthSession.token_digest == digest, AuthSession.revoked_at.is_(None),
            ).values(revoked_at=utc_now()))
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="strict")
    return response


@router.get("/organizations")
def list_organizations(request: Request):
    user = require_user(request)
    with platform_session() as db:
        items = db.execute(select(Organization.id, Organization.name, Membership.role).join(
            Membership, Membership.org_id == Organization.id,
        ).where(Membership.user_id == user.id, Membership.revoked_at.is_(None))
            .order_by(Organization.name, Organization.id)).mappings()
        return {"organizations": [dict(item) for item in items]}


@router.post("/organizations", status_code=201)
def create_organization(body: NamedResource, request: Request):
    user = require_user(request)
    with platform_session() as db:
        org = Organization(name=body.name)
        db.add(org)
        db.flush()
        db.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
        return {"id": org.id, "name": org.name, "role": "owner"}


@router.get("/organizations/{org_id}/members")
def list_members(org_id: str, request: Request):
    user = require_user(request)
    with platform_session() as db:
        actor = require_membership(db, org_id, user.id)
        if actor.role not in MANAGERS:
            raise HTTPException(403, "إدارة أعضاء المؤسسة تتطلب صلاحية.")
        items = db.execute(select(Membership.user_id, Membership.role, User.display_name).join(
            User, User.id == Membership.user_id,
        ).where(Membership.org_id == org_id, Membership.revoked_at.is_(None),
                User.disabled_at.is_(None)).order_by(User.display_name, User.id)).mappings()
        return {"members": [member_view(item) for item in items]}


@router.post("/organizations/{org_id}/members")
def add_member(org_id: str, body: MemberInput, request: Request):
    user = require_user(request)
    with platform_session() as db:
        actor = require_membership(db, org_id, user.id)
        if actor.role != "owner":
            raise HTTPException(403, "تعديل عضوية المؤسسة يتطلب صلاحية المالك.")
        member = require_membership(db, org_id, body.user_id)
        if member.role == "owner":
            raise HTTPException(409, "دور مالك المؤسسة ثابت.")
        member.role = body.role
        return {"user_id": body.user_id, "role": body.role}


@router.delete("/organizations/{org_id}/members/{user_id}", status_code=204)
def remove_member(org_id: str, user_id: str, request: Request):
    actor = require_user(request)
    with platform_session() as db:
        if require_membership(db, org_id, actor.id).role != "owner":
            raise HTTPException(403, "تعديل عضوية المؤسسة يتطلب صلاحية المالك.")
        member = require_membership(db, org_id, user_id)
        if member.role == "owner":
            raise HTTPException(409, "عضوية مالك المؤسسة ثابتة.")
        now = utc_now()
        member.revoked_at = now
        db.execute(update(ProjectGrant).where(
            ProjectGrant.org_id == org_id, ProjectGrant.user_id == user_id, ProjectGrant.revoked_at.is_(None),
        ).values(revoked_at=now))


@router.post("/organizations/{org_id}/projects", status_code=201)
def create_project(org_id: str, body: NamedResource, request: Request):
    user = require_user(request)
    with platform_session() as db:
        member = require_membership(db, org_id, user.id)
        if member.role not in MANAGERS:
            raise HTTPException(403, "إنشاء المشروع يتطلب صلاحية إدارة المؤسسة.")
        project = Project(org_id=org_id, name=body.name)
        db.add(project)
        db.flush()
        return {"id": project.id, "org_id": org_id, "name": project.name, "role": member.role}


@router.get("/projects")
def list_projects(request: Request):
    user = require_user(request)
    with platform_session() as db:
        items = db.execute(select(Project.id, Project.org_id, Project.name, Membership.role).join(
            Membership, and_(Membership.org_id == Project.org_id, Membership.user_id == user.id,
                             Membership.revoked_at.is_(None)),
        ).outerjoin(ProjectGrant, and_(
            ProjectGrant.org_id == Project.org_id, ProjectGrant.project_id == Project.id,
            ProjectGrant.user_id == user.id, ProjectGrant.revoked_at.is_(None),
        )).where(or_(Membership.role.in_(MANAGERS), ProjectGrant.user_id.is_not(None)))
            .order_by(Project.name, Project.id)).mappings()
        return {"projects": [dict(item) for item in items]}


@router.get("/projects/{project_id}/grants")
def list_grants(project_id: str, request: Request):
    context = require_project(request, project_id, "manage")
    with platform_session() as db:
        items = db.execute(select(ProjectGrant.user_id, Membership.role, User.display_name).join(
            Membership, and_(Membership.org_id == ProjectGrant.org_id,
                             Membership.user_id == ProjectGrant.user_id),
        ).join(User, User.id == ProjectGrant.user_id).where(
            ProjectGrant.org_id == context.org_id, ProjectGrant.project_id == context.project_id,
            ProjectGrant.revoked_at.is_(None), Membership.revoked_at.is_(None), User.disabled_at.is_(None),
        ).order_by(User.display_name, User.id)).mappings()
        return {"grants": [member_view(item) for item in items]}


@router.post("/projects/{project_id}/grants")
def add_grant(project_id: str, body: GrantInput, request: Request):
    context = require_project(request, project_id, "manage")
    with platform_session() as db:
        member = require_membership(db, context.org_id, body.user_id)
        if member.role in MANAGERS:
            raise HTTPException(409, "عضو الإدارة عنده صلاحية المشروع بالفعل.")
        grant = db.get(ProjectGrant, (context.org_id, project_id, body.user_id))
        if grant:
            grant.revoked_at = None
            grant.granted_at = utc_now()
        else:
            db.add(ProjectGrant(org_id=context.org_id, project_id=project_id, user_id=body.user_id))
        return {"user_id": body.user_id}


@router.delete("/projects/{project_id}/grants/{user_id}", status_code=204)
def remove_grant(project_id: str, user_id: str, request: Request):
    context = require_project(request, project_id, "manage")
    with platform_session() as db:
        db.execute(update(ProjectGrant).where(
            ProjectGrant.org_id == context.org_id, ProjectGrant.project_id == context.project_id,
            ProjectGrant.user_id == user_id, ProjectGrant.revoked_at.is_(None),
        ).values(revoked_at=utc_now()))


def install_identity(app):
    from .organization_invitations import router as invitation_router

    state_secret = os.environ.get("MARSAD_OIDC_STATE_SECRET", "")
    redirect_uri = os.environ.get("MARSAD_OIDC_REDIRECT_URI", "")
    if len(state_secret) >= 32 and endpoint_allowed(redirect_uri):
        app.add_middleware(SessionMiddleware, secret_key=state_secret, session_cookie=STATE_COOKIE,
                           max_age=600, path="/api/platform/auth", same_site="lax",
                           https_only=urlsplit(redirect_uri).scheme == "https")

    @app.exception_handler(PlatformUnavailable)
    async def platform_unavailable(_request, _error):
        return JSONResponse({"detail": "إعدادات منصة المشاريع غير مفعّلة."}, status_code=503,
                            headers={"Cache-Control": "no-store"})

    app.include_router(router)
    app.include_router(invitation_router)
    from .password_auth import router as password_router
    app.include_router(password_router)
