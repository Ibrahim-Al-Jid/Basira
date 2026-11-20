import pytest
from fastapi.testclient import TestClient
import sqlalchemy as sa

from .identity import SESSION_COOKIE
from .main import app
from .platform_db import Base, User, database_engine, platform_session
from .password_auth import credentials

EMAIL = "local-owner@example.test"
PASSWORD = "separate test passphrase 64"
BASE = "http://127.0.0.1:8765"
AUTH = "/api/platform/auth"


@pytest.fixture
def accounts(monkeypatch, tmp_path):
    url = "sqlite:///" + (tmp_path / "password.sqlite3").as_posix()
    monkeypatch.setenv("MARSAD_DB_PATH", str(tmp_path / "lab.sqlite3"))
    monkeypatch.setenv("MARSAD_PLATFORM_DATABASE_URL", url)
    monkeypatch.setenv("MARSAD_PASSWORD_AUTH_ENABLED", "1")
    monkeypatch.setenv("MARSAD_PASSWORD_SELF_SIGNUP", "1")
    engine = database_engine(url)
    Base.metadata.create_all(engine)
    with TestClient(app, base_url=BASE) as first, TestClient(app, base_url=BASE) as other:
        yield first, other
    engine.dispose()


def authenticate(client, action, email=EMAIL, password=PASSWORD):
    return client.post(AUTH + "/password/" + action, json={"email": email, "password": password})


def test_register_login_revoke_and_tenant_boundary(accounts):
    owner, other = accounts
    assert owner.get(AUTH + "/options").json() == {"oidc": False, "password": True, "registration": True}
    assert authenticate(owner, "register", password="short").status_code == 422
    rejected = authenticate(owner, "register", email="invalid-email", password=PASSWORD * 6)
    assert rejected.status_code == 422
    assert "الإيميل" in rejected.json()["detail"]
    assert "invalid-email" not in rejected.text
    assert PASSWORD not in rejected.text
    response = authenticate(owner, "register", email=EMAIL.upper())
    assert response.status_code == 201
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    account = response.json()
    assert account["display_name"] == EMAIL
    assert owner.get(AUTH + "/me").json() == account
    with platform_session() as db:
        stored = db.execute(sa.select(credentials.c.password_hash)).scalar_one()
        assert stored.startswith("$argon2id$")
        assert PASSWORD not in stored
    assert authenticate(other, "register").status_code == 409
    old_cookie = owner.cookies.get(SESSION_COOKIE)
    response = authenticate(owner, "login")
    assert response.json() == account
    assert owner.cookies.get(SESSION_COOKIE) != old_cookie
    assert owner.get(AUTH + "/me", headers={"Cookie": f"{SESSION_COOKIE}={old_cookie}"}).status_code == 401

    org = owner.post("/api/platform/organizations", json={"name": "Private"}).json()["id"]
    project = owner.post(f"/api/platform/organizations/{org}/projects", json={"name": "Private"}).json()["id"]
    assert authenticate(other, "register", "other@example.test").status_code == 201
    assert other.get(f"/api/platform/projects/{project}/scans").status_code == 404
    assert owner.post(AUTH + "/logout").status_code == 204
    assert owner.get(AUTH + "/me").status_code == 401
    assert authenticate(owner, "login").status_code == 200
    assert owner.get(f"/api/platform/projects/{project}/scans").status_code == 200


def test_throttle_and_generic_rejection(accounts):
    owner, other = accounts
    assert authenticate(owner, "register").status_code == 201
    missing = authenticate(other, "login", "missing@example.test", "incorrect")
    assert missing.status_code == 401
    for _ in range(8):
        wrong = authenticate(other, "login", password="incorrect")
        assert wrong.status_code == 401
        assert wrong.json() == missing.json()
    limited = authenticate(other, "login")
    assert limited.status_code == 429
    assert limited.headers["retry-after"]


def test_signup_scoped_to_local_and_disabled_user_denied(accounts, monkeypatch):
    owner, _ = accounts
    assert authenticate(owner, "register").status_code == 201
    monkeypatch.setenv("MARSAD_PASSWORD_SELF_SIGNUP", "0")
    assert authenticate(owner, "register", "blocked@example.test").status_code == 403
    with TestClient(app, base_url="http://public.example.test") as public:
        assert authenticate(public, "login").status_code == 403
    with TestClient(app, base_url="https://public.example.test") as public:
        assert authenticate(public, "login").status_code == 403
    with TestClient(app, base_url="https://127.0.0.1:8765") as secure:
        result = authenticate(secure, "login")
        assert result.status_code == 200
        assert "Secure" in result.headers["set-cookie"]
    with platform_session() as db:
        from .platform_db import utc_now
        user = db.scalar(sa.select(User).where(User.subject == EMAIL))
        user.disabled_at = utc_now()
    assert owner.get(AUTH + "/me").status_code == 401
    assert authenticate(owner, "login").status_code == 401


def test_existing_local_session_denied_when_login_disabled(accounts, monkeypatch):
    owner, _ = accounts
    assert authenticate(owner, "register").status_code == 201
    assert owner.get(AUTH + "/me").status_code == 200
    monkeypatch.setenv("MARSAD_PASSWORD_AUTH_ENABLED", "0")
    assert owner.get(AUTH + "/me").status_code == 401
    assert owner.get(AUTH + "/options").json()["password"] is False
