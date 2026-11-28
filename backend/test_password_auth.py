from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from fastapi.testclient import TestClient
import sqlalchemy as sa

from .identity import SESSION_COOKIE
from .main import app
from .platform_db import Base, User, database_engine, platform_session
from .password_auth import HASHER, credentials

EMAIL = "local-owner@example.test"
PASSWORD = "separate test passphrase 64"
BASE = "http://127.0.0.1:8765"
AUTH = "/api/platform/auth"


@pytest.fixture
def accounts(monkeypatch, tmp_path):
    url = "sqlite:///" + (tmp_path / "password.sqlite3").as_posix()
    monkeypatch.setenv("BASIRA_PLATFORM_DATABASE_URL", url)
    monkeypatch.setenv("BASIRA_PASSWORD_AUTH_ENABLED", "1")
    monkeypatch.setenv("BASIRA_PASSWORD_SELF_SIGNUP", "1")
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
    assert account["display_name"] == ""
    assert EMAIL not in response.text
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
    monkeypatch.setenv("BASIRA_PASSWORD_SELF_SIGNUP", "0")
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
    monkeypatch.setenv("BASIRA_PASSWORD_AUTH_ENABLED", "0")
    assert owner.get(AUTH + "/me").status_code == 401
    assert owner.get(AUTH + "/options").json()["password"] is False


def test_signup_names_and_private_profile_updates(accounts):
    owner, other = accounts
    named = {"email": EMAIL, "password": PASSWORD, "first_name": "إبراهيم", "last_name": "حمدي"}
    incomplete = dict(named)
    incomplete.pop("last_name")
    assert owner.post(AUTH + "/password/register", json=incomplete).status_code == 422
    invalid_name = "_Surname12"
    rejected = owner.post(AUTH + "/password/register", json={**named, "last_name": invalid_name})
    assert rejected.status_code == 422
    assert rejected.json()["fields"] == ["last_name"]
    assert "اسم العائلة" in rejected.json()["detail"]
    assert invalid_name not in rejected.text and PASSWORD not in rejected.text
    created = owner.post(AUTH + "/password/register", json=named)
    assert created.status_code == 201
    account = created.json()
    assert account["display_name"] == "إبراهيم حمدي"
    assert account["username"] is None and account["created_at"]
    assert EMAIL not in created.text

    profile = {"first_name": "إبراهيم", "last_name": "حمدي", "username": "Ibrahim.H"}
    assert other.put(AUTH + "/profile", json=profile).status_code == 401
    assert owner.put(AUTH + "/profile", json={**profile, "id": "another-account"}).status_code == 422
    foreign = owner.put(AUTH + "/profile", json=profile, headers={"Origin": "https://foreign.example.test"})
    assert foreign.status_code == 403
    assert owner.put(AUTH + "/profile", json={**profile, "first_name": EMAIL}).status_code == 422
    changed = owner.put(AUTH + "/profile", json=profile)
    assert changed.status_code == 200
    assert changed.headers["cache-control"] == "no-store"
    assert changed.json() == {**account, "username": "ibrahim.h"}
    assert owner.get(AUTH + "/me").json() == changed.json()

    assert authenticate(other, "register", "other@example.test").status_code == 201
    assert other.put(AUTH + "/profile", json={**profile, "username": "IBRAHIM.h"}).status_code == 409
    assert other.get(AUTH + "/me").json()["display_name"] == ""
    assert owner.put(AUTH + "/profile", json={**profile, "username": None}).json()["username"] is None
    assert other.put(AUTH + "/profile", json=profile).status_code == 200
    assert authenticate(owner, "login").json() == account


def test_existing_password_account_survives_profile_migration(monkeypatch, tmp_path):
    url = "sqlite:///" + (tmp_path / "legacy.sqlite3").as_posix()
    for key in ("BASIRA_PLATFORM_DATABASE_URL", "BASIRA_PLATFORM_MIGRATION_URL"):
        monkeypatch.setenv(key, url)
    monkeypatch.setenv("BASIRA_PASSWORD_AUTH_ENABLED", "1")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "platform_models_0008")
    engine = database_engine(url)
    account_id = "a" * 32
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO users (id, issuer, subject, display_name, created_at) "
                "VALUES (:id, 'urn:basira:password', :email, :email, '2025-01-01 10:00:00')"
            ), {"id": account_id, "email": EMAIL})
            conn.execute(credentials.insert().values(user_id=account_id, password_hash=HASHER.hash(PASSWORD)))
        command.upgrade(config, "platform_profiles_0009")
        with TestClient(app, base_url=BASE) as client:
            login = authenticate(client, "login")
            assert login.status_code == 200
            assert login.json() == {
                "id": account_id, "display_name": "", "first_name": None, "last_name": None,
                "username": None, "created_at": "2025-01-01T10:00:00+00:00",
            }
    finally:
        engine.dispose()
