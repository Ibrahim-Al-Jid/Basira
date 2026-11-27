from base64 import urlsafe_b64encode
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey
import pytest
from sqlalchemy import inspect, update

from . import identity
from .identity import oidc_httpx as httpx
from .organization_invitations import OrganizationInvitation
from .platform_db import AuthSession, Base, database_engine, platform_session, utc_now


ISSUER = "https://oidc.example/realm"
CLIENT_ID = "basira-fixture"
APP_ORIGIN = "https://basira.example"


@pytest.fixture
def platform(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "platform.sqlite3").as_posix()
    for name, value in {
        "BASIRA_PLATFORM_DATABASE_URL": url,
        "BASIRA_PLATFORM_MIGRATION_URL": url,
        "BASIRA_OIDC_ISSUER": ISSUER,
        "BASIRA_OIDC_CLIENT_ID": CLIENT_ID,
        "BASIRA_OIDC_CLIENT_SECRET": "example-credential-for-test",
        "BASIRA_OIDC_REDIRECT_URI": APP_ORIGIN + "/api/platform/auth/callback",
        "BASIRA_OIDC_STATE_SECRET": "test-secret-for-cookie-signing-only",
    }.items():
        monkeypatch.setenv(name, value)
    engine = database_engine(url)
    Base.metadata.create_all(engine)
    app = FastAPI()
    identity.install_identity(app)

    @app.get("/api/platform/fixture/{project_id}/{action}")
    def project_permission(project_id: str, action: str, request: Request):
        return identity.require_project(request, project_id, action)

    yield app
    engine.dispose()


def claims_for(subject, **overrides):
    now = int(utc_now().timestamp())
    return {"iss": ISSUER, "aud": CLIENT_ID, "sub": subject, "name": subject,
            "iat": now, "exp": now + 600, **overrides}


def actor(app, subject):
    token = identity.persist_login(identity.oidc_settings(), claims_for(subject), None)
    client = TestClient(app, base_url=APP_ORIGIN)
    client.cookies.set(identity.SESSION_COOKIE, token)
    user_id = client.get("/api/platform/auth/me").json()["id"]
    return client, user_id, token


def invite_member(owner, member, org_id, role):
    invite = owner.post(f"/api/platform/organizations/{org_id}/invitations", json={"role": role})
    assert invite.status_code == 201, invite.text
    joined = member.post("/api/platform/invitations/accept", json={"token": invite.json()["token"]})
    assert joined.status_code == 200, joined.text
    assert joined.json()["org_id"] == org_id and joined.json()["role"] == role


def test_invitation_scope_replay_expiry_and_revocation(platform):
    owner, _, _ = actor(platform, "invite-owner")
    recipient, recipient_id, _ = actor(platform, "invitee")
    foreign, _, _ = actor(platform, "invite-foreign")
    orgs = "/api/platform/organizations"
    org = owner.post(orgs, json={"name": "Inviting team"}).json()["id"]
    other_org = foreign.post(orgs, json={"name": "Other team"}).json()["id"]
    path = f"{orgs}/{org}/invitations"
    accept = "/api/platform/invitations/accept"
    assert owner.post(f"{orgs}/{org}/members", json={"user_id": recipient_id, "role": "admin"}).status_code == 404
    assert foreign.post(path, json={"role": "admin"}).status_code == 404
    assert owner.post(path, json={"role": "owner"}).status_code == 422
    created = owner.post(path, json={"role": "viewer"}).json()
    token = created["token"]
    assert token not in owner.get(path).text
    payload = {"token": token}
    with platform_session() as db:
        invitation = db.get(OrganizationInvitation, created["id"])
        assert invitation.token_digest == sha256(token.encode()).hexdigest()
    assert foreign.delete(f"{orgs}/{other_org}/invitations/{created['id']}").status_code == 404
    assert recipient.post(accept, json=payload).json()["role"] == "viewer"
    assert recipient.post(accept, json=payload).status_code == 404
    assert recipient.get(path).status_code == 403
    revoked = owner.post(path, json={"role": "admin"}).json()
    assert owner.delete(f"{path}/{revoked['id']}").status_code == 204
    assert foreign.post(accept, json={"token": revoked["token"]}).status_code == 404
    expired = owner.post(path, json={"role": "analyst"}).json()
    with platform_session() as db:
        db.get(OrganizationInvitation, expired["id"]).expires_at = utc_now() - timedelta(seconds=1)
    assert foreign.post(accept, json={"token": expired["token"]}).status_code == 404
    assert owner.get(path).json() == {"invitations": []}


def test_oidc_pkce_and_verified_jwt(platform):
    client = TestClient(platform, base_url=APP_ORIGIN, follow_redirects=False)
    rsa = RSAKey.generate_key(parameters={"kid": "fixture-signing-key"})
    challenges = {}
    token_requests = []
    claims_override = {}

    def provider(request):
        if request.url.path == "/realm/.well-known/openid-configuration":
            return httpx.Response(200, json={
                "issuer": ISSUER, "authorization_endpoint": ISSUER + "/authorize",
                "token_endpoint": ISSUER + "/token", "jwks_uri": ISSUER + "/jwks",
                "id_token_signing_alg_values_supported": ["RS256", "none"],
            })
        if request.url.path == "/realm/jwks":
            return httpx.Response(200, json={"keys": [rsa.as_dict()]})
        assert request.url.path == "/realm/token"
        token_requests.append(request)
        body = parse_qs(request.content.decode())
        verifier = body["code_verifier"][0]
        code = body["code"][0]
        expected = challenges.pop(code)
        challenge = urlsafe_b64encode(sha256(verifier.encode()).digest()).decode().rstrip("=")
        assert challenge == expected["code_challenge"][0]
        assert body["redirect_uri"] == [APP_ORIGIN + "/api/platform/auth/callback"]
        claims = claims_for("signed-user", nonce=expected["nonce"][0])
        claims.update(claims_override)
        id_token = jwt.encode({"alg": "RS256", "kid": "fixture-signing-key"}, claims, rsa)
        return httpx.Response(200, json={"access_token": "fixture-access-token", "id_token": id_token,
                                         "token_type": "Bearer"})

    identity.oauth_client.cache_clear()
    oauth = identity.oauth_client(identity.oidc_settings())
    oauth.client_kwargs["transport"] = httpx.MockTransport(provider)

    def begin(code):
        redirect = client.get("/api/platform/auth/login")
        assert redirect.status_code == 302
        cookie = redirect.headers["set-cookie"].lower()
        assert "httponly" in cookie and "secure" in cookie
        params = parse_qs(urlsplit(redirect.headers["location"]).query)
        assert params["code_challenge_method"] == ["S256"]
        assert params["response_type"] == ["code"]
        challenges[code] = params
        return params["state"][0]

    try:
        state = begin("verified")
        wrong = client.get("/api/platform/auth/callback", params={"code": "verified", "state": "wrong"})
        assert wrong.status_code == 400
        assert not token_requests
        callback = client.get("/api/platform/auth/callback", params={"code": "verified", "state": state})
        assert callback.status_code == 303
        assert callback.headers["location"] == "/dashboard"
        assert "SameSite=strict" in callback.headers["set-cookie"]
        assert client.get("/api/platform/auth/me").json()["display_name"] == "signed-user"
        session = client.cookies.get(identity.SESSION_COOKIE)
        with platform_session() as db:
            row = db.get(AuthSession, identity.token_digest(session))
            assert row is not None and row.token_digest != session
            assert row.expires_at - row.created_at == identity.SESSION_TTL
        assert client.get("/api/platform/auth/callback", params={"code": "verified", "state": state}).status_code == 400
        for code, override in (
            ("wrong-nonce", {"nonce": "wrong"}),
            ("wrong-audience", {"aud": "another-app"}),
            ("wrong-issuer", {"iss": "https://other-issuer.example"}),
        ):
            state = begin(code)
            claims_override.clear()
            claims_override.update(override)
            failure = client.get("/api/platform/auth/callback", params={"code": code, "state": state})
            assert failure.status_code == 400
            assert "fixture-access-token" not in failure.text
    finally:
        identity.oauth_client.cache_clear()


def test_revoked_and_expired_sessions(platform):
    client, _, token = actor(platform, "revoked")
    assert client.post("/api/platform/auth/logout").status_code == 204
    client.cookies.set(identity.SESSION_COOKIE, token)
    assert client.get("/api/platform/auth/me").status_code == 401
    expired, _, expired_token = actor(platform, "expired")
    with platform_session() as db:
        when = utc_now()
        db.execute(update(AuthSession).where(AuthSession.token_digest == identity.token_digest(expired_token)).values(
            created_at=when - timedelta(hours=2), expires_at=when - timedelta(hours=1),
        ))
    assert expired.get("/api/platform/projects").status_code == 401
    missing = TestClient(platform)
    assert missing.get("/api/platform/projects").status_code == 401


def test_project_access_and_role_changes(platform):
    owner, _, _ = actor(platform, "owner")
    viewer, viewer_id, _ = actor(platform, "viewer")
    analyst, analyst_id, _ = actor(platform, "analyst")
    admin, admin_id, _ = actor(platform, "admin")
    foreign_owner, _, _ = actor(platform, "second-tenant-owner")
    orgs = "/api/platform/organizations"
    org = owner.post(orgs, json={"name": "One"}).json()["id"]
    other = foreign_owner.post(orgs, json={"name": "Two"}).json()["id"]
    organization = f"{orgs}/{org}"
    project = owner.post(organization + "/projects", json={"name": "Demo"}).json()["id"]
    hidden = owner.post(organization + "/projects", json={"name": "Hidden"}).json()["id"]
    foreign_project = foreign_owner.post(f"{orgs}/{other}/projects", json={"name": "Foreign"}).json()["id"]
    grants = f"/api/platform/projects/{project}/grants"

    for account, role in ((viewer, "viewer"), (analyst, "analyst"), (admin, "admin")):
        invite_member(owner, account, org, role)
    assert viewer.get("/api/platform/projects").json() == {"projects": []}
    assert len(admin.get("/api/platform/projects").json()["projects"]) == 2
    for account in (viewer_id, analyst_id):
        assert admin.post(grants, json={"user_id": account}).status_code == 200
    assert owner.get(grants).json()["grants"][0]["role"] in {"viewer", "analyst"}
    assert len(owner.get(grants).json()["grants"]) == 2
    assert [row["id"] for row in viewer.get("/api/platform/projects").json()["projects"]] == [project]
    assert viewer.get(f"/api/platform/fixture/{project}/read").status_code == 200
    assert viewer.get(f"/api/platform/fixture/{project}/scan").status_code == 403
    assert viewer.get(f"/api/platform/fixture/{hidden}/read").status_code == 404
    assert analyst.get(f"/api/platform/fixture/{project}/scan").json()["role"] == "analyst"
    assert analyst.get(f"/api/platform/fixture/{project}/manage").status_code == 403
    assert admin.post(organization + "/members", json={"user_id": viewer_id, "role": "admin"}).status_code == 403
    assert owner.get(f"/api/platform/fixture/{foreign_project}/read").status_code == 404
    assert foreign_owner.get(grants).status_code == 404
    assert owner.delete(f"{organization}/members/{viewer_id}").status_code == 204
    assert viewer.get(f"/api/platform/fixture/{project}/read").status_code == 404
    invite_member(owner, viewer, org, "viewer")
    assert viewer.get(f"/api/platform/fixture/{project}/read").status_code == 404
    assert admin.delete(f"{grants}/{analyst_id}").status_code == 204
    assert analyst.get(f"/api/platform/fixture/{project}/scan").status_code == 404


def test_identity_migration_from_empty_database(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "migration.sqlite3").as_posix()
    monkeypatch.setenv("BASIRA_PLATFORM_MIGRATION_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "platform_identity_0001")
    engine = database_engine(url)
    try:
        schema = inspect(engine)
        assert set(schema.get_table_names()) >= {
            "users", "auth_sessions", "organizations", "memberships", "projects", "project_grants",
        }
        assert {item["name"] for item in schema.get_foreign_keys("project_grants")} == {
            "fk_project_grants_membership", "fk_project_grants_project",
        }
    finally:
        engine.dispose()
