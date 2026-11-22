from base64 import b64encode, urlsafe_b64encode
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from . import model_connections, model_gateway, platform_runtime as store
from .main import app
from .platform_db import Base, GitHubConnection, database_engine, platform_session, utc_now

BASE = "http://127.0.0.1:8765"
API = "/api/platform"


@pytest.fixture
def personal_clients(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "personal.sqlite3").as_posix()
    monkeypatch.setenv("MARSAD_PLATFORM_DATABASE_URL", url)
    monkeypatch.setenv("MARSAD_DB_PATH", str(tmp_path / "lab.sqlite3"))
    for flag in ("MARSAD_PERSONAL_PROJECTS", "MARSAD_PASSWORD_AUTH_ENABLED", "MARSAD_PASSWORD_SELF_SIGNUP"):
        monkeypatch.setenv(flag, "1")
    engine = database_engine(url)
    Base.metadata.create_all(engine)
    with TestClient(app, base_url=BASE) as owner, TestClient(app, base_url=BASE) as other:
        for index, client in enumerate((owner, other)):
            response = client.post(API + "/auth/password/register", json={
                "email": f"account-{index}@example.test", "password": "separate password for this test",
            })
            assert response.status_code == 201
        yield owner, other
    engine.dispose()


def repository_submission():
    archive = BytesIO()
    with ZipFile(archive, "w") as file:
        file.writestr("index.html", "<html lang='en'><title>Fixture</title></html>")
    return {"kind": "repository", "name": "sample.zip", "content": b64encode(archive.getvalue()).decode()}


def test_personal_crud_scan_and_archive_are_owner_only(personal_clients):
    owner, other = personal_clients
    created = owner.post(API + "/projects", json={"name": "First project"})
    assert created.status_code == 201
    project = created.json()
    assert "org_id" not in project
    path = API + "/projects/" + project["id"]
    assert owner.get(API + "/projects").json()["projects"] == [project]
    assert other.get(API + "/projects").json()["projects"] == []
    assert other.get(path).status_code == 404
    assert other.patch(path, json={"name": "Wrong owner"}).status_code == 404
    assert other.delete(path).status_code == 404
    assert owner.patch(path, json={"name": "Renamed project"}).json()["name"] == "Renamed project"
    assert owner.patch(path, json={"name": "Block foreign origin"}, headers={"Origin": "https://other.example"}).status_code == 403

    body = repository_submission()
    headers = {"Idempotency-Key": "personal-scan-01"}
    assert other.post(path + "/scans", json=body, headers=headers).status_code == 404
    rejected = owner.post(path + "/scans", headers=headers, json={
        "kind": "html", "name": "sample.html", "content": b64encode(b"<p>fixture</p>").decode(),
    })
    assert rejected.status_code == 422
    assert owner.get(path + "/scan-profile").json()["allowed_kinds"] == ["repository"]
    scan = owner.post(path + "/scans", json=body, headers=headers)
    assert scan.status_code == 202
    scan_id = scan.json()["id"]
    for route in ("/scans", f"/scans/{scan_id}", f"/scans/{scan_id}/provenance",
                  f"/scans/{scan_id}/evidence", "/reports", f"/reports/{scan_id}/download?format=pdf"):
        assert other.get(path + route).status_code == 404
    assert other.post(path + f"/scans/{scan_id}/cancel").status_code == 404
    with platform_session() as db:
        org_id = db.execute(text("SELECT org_id FROM projects WHERE id = :id"), {"id": project["id"]}).scalar_one()
    lease = store.claim(org_id, project["id"], scan_id)["lease"]
    assert owner.delete(path).status_code == 204
    assert owner.get(path).status_code == 404
    assert owner.get(path + "/reports").status_code == 404
    assert not store.finish(org_id, project["id"], scan_id, lease, report={})
    with platform_session() as db:
        record = db.execute(text("SELECT state, raw FROM project_scans WHERE id = :id"), {"id": scan_id}).one()
        assert tuple(record) == ("cancelled", None)


def test_personal_mode_closes_legacy_routes_and_keeps_github_metadata_private(personal_clients):
    owner, other = personal_clients
    assert owner.get("/api/product").json() == {"personal_projects": True}
    project = owner.post(API + "/projects", json={"name": "Repository"}).json()["id"]
    for path in ("/demo", "/demo/", "/api/history", "/api/reports/old", API + "/organizations",
                 API + f"/projects/{project}/grants", API + f"/projects/{project}/github-source"):
        assert owner.get(path).status_code == 404
    assert owner.post("/api/run", json={}).status_code == 404
    assert owner.post(API + "/invitations/accept", json={}).status_code == 404
    assert owner.post(API + f"/projects/{project}/reports/old/claim", json={}).status_code == 404

    with platform_session() as db:
        db.add(GitHubConnection(user_id=owner.get(API + "/auth/me").json()["id"], installation_id="1",
                                provider_account_id="2", status="verified", verified_at=utc_now()))
    assert owner.get(API + "/github-connections").json()["connections"] == [
        {"installation_id": "1", "provider_account_id": "2"},
    ]
    assert other.get(API + "/github-connections").json() == {"connections": [], "connect_available": False}


def test_account_catalog_and_scan_use_only_the_owners_saved_credential(personal_clients, monkeypatch, tmp_path):
    owner, other = personal_clients
    endpoint = API + "/account/model-connection"
    key = "test-key-only-for-fixtures"
    free = "fixture/free:free"
    paid = "fixture/paid"
    vault = tmp_path / "vault.key"
    vault.write_bytes(urlsafe_b64encode(bytes(32)))
    monkeypatch.setenv("MARSAD_MODEL_MASTER_KEY_FILE", str(vault))
    monkeypatch.setenv("MARSAD_GATEWAY_URL", "http://gateway.example")
    monkeypatch.setenv("MARSAD_GATEWAY_TOKEN", "fixture-token")
    monkeypatch.setattr(model_gateway, "provider_models", lambda supplied: [
        {"id": free, "name": "Free model", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": paid, "name": "Paid model", "pricing": {"prompt": "0", "completion": "0", "request": "0.1"}},
        {"id": "fixture/image", "architecture": {"output_modalities": ["image"]}},
    ] if supplied == key else [])
    monkeypatch.setattr(model_gateway, "provider_order", lambda supplied, model, counts: (
        {"priority": list(counts)} if supplied == key and model == free else pytest.fail("Wrong model credential")
    ))
    with TestClient(model_gateway.app) as gateway:
        monkeypatch.setattr(model_connections.httpx, "get", lambda url, headers, **_: gateway.get(
            url.removeprefix("http://gateway.example"), headers=headers))
        monkeypatch.setattr(model_connections.httpx, "post", lambda url, headers, json, **_: gateway.post(
            url.removeprefix("http://gateway.example"), headers=headers, json=json))
        origin = {"Origin": BASE}
        catalog = owner.post(endpoint + "/models", headers=origin, json={"api_key": key})
        assert catalog.json() == {"models": [
            {"id": free, "name": "Free model", "free": True},
            {"id": paid, "name": "Paid model", "free": False},
        ]}
        assert key not in catalog.text and catalog.headers["cache-control"] == "no-store"
        assert owner.put(endpoint, json={"api_key": key, "model": free}).status_code == 403
        saved = owner.put(endpoint, headers=origin, json={"api_key": key, "model": free})
        assert saved.status_code == 200 and key not in saved.text
        assert owner.post(endpoint + "/models", headers=origin, json={}).json() == catalog.json()
        assert other.get(endpoint).json()["connection"] is None
        assert other.post(endpoint + "/models", headers=origin, json={}).status_code == 422
        project_id = owner.post(API + "/projects", json={"name": "Personal model scan"}).json()["id"]
        project = API + "/projects/" + project_id
        profile = owner.get(project + "/scan-profile").json()
        assert profile["model_connection"]["model"] == free
        scan = owner.post(project + "/scans", headers={"Idempotency-Key": "personal-model-test"}, json={
            **repository_submission(), "scope_version": profile["scope_version"],
            "acknowledge_scope": True, "model_connection": "openrouter-default",
        })
        assert scan.status_code == 202
        scan_id = scan.json()["id"]
        with platform_session() as db:
            org_id = db.execute(text("SELECT org_id FROM projects WHERE id = :id"), {"id": project_id}).scalar_one()
        job = store.claim(org_id, project_id, scan_id)
        connection = store.reserve_model_connection(org_id, project_id, scan_id, job["lease"])
        report = {"findings": [{"rule": "http-script"}], "metrics": {"modelCalls": 0}}
        model_gateway.enrich(report, connection, org_id=org_id, project_id=project_id, scan_id=scan_id, lease=job["lease"])
        assert report["enrichment"] == "model"
        assert report["metrics"]["modelCalls"] == 1
        assert owner.delete(endpoint, headers=origin).json()["connection"] is None


def test_backfill_quarantines_shared_and_ownerless_projects(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "migration.sqlite3").as_posix()
    monkeypatch.setenv("MARSAD_PLATFORM_MIGRATION_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("script_location", str(root / "backend" / "migrations"))
    command.upgrade(config, "platform_evidence_links_0011")
    engine = database_engine(url)
    with engine.begin() as db:
        for account in ("owner", "member", "disabled"):
            db.execute(text("""INSERT INTO users (id, issuer, subject, display_name, created_at, disabled_at)
                VALUES (:id, 'fixture', :id, '', :now, :disabled)"""), {
                "id": account, "now": utc_now() - timedelta(days=2),
                "disabled": utc_now() if account == "disabled" else None,
            })
        for name, account in (("personal", "owner"), ("shared", "owner"), ("ownerless", "disabled")):
            db.execute(text("INSERT INTO organizations (id, name, created_at) VALUES (:id, :id, :now)"),
                       {"id": name, "now": utc_now()})
            db.execute(text("INSERT INTO projects (id, org_id, name, created_at) VALUES (:id, :id, :id, :now)"),
                       {"id": name, "now": utc_now()})
            db.execute(text("""INSERT INTO memberships (org_id, user_id, role, joined_at)
                VALUES (:org, :owner, 'owner', :now)"""), {"org": name, "owner": account, "now": utc_now()})
        db.execute(text("""INSERT INTO memberships (org_id, user_id, role, joined_at)
                         VALUES ('shared', 'member', 'viewer', :now)"""), {"now": utc_now()})
    command.upgrade(config, "head")
    with engine.begin() as db:
        owners = {project_id: user_id for project_id, user_id in db.execute(text("SELECT id, owner_user_id FROM projects"))}
        reviews = {project_id: reason for project_id, reason in db.execute(text("SELECT project_id, reason FROM project_ownership_reviews"))}
    assert owners == {"personal": "owner", "shared": None, "ownerless": None}
    assert reviews == {"shared": "shared_membership_or_grant", "ownerless": "missing_owner"}
    engine.dispose()
