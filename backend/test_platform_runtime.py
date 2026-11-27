import base64
from datetime import timedelta
import io
import json
import os
import sqlite3
import time
from types import SimpleNamespace
from zipfile import ZipFile, ZipInfo

from fastapi.testclient import TestClient
import httpx
import pytest
import sqlalchemy as sa

from . import main, model_gateway, platform_jobs as jobs, platform_runtime as store
from .artifact_review import InputError, defensive_review, zip_texts
from .identity import SESSION_COOKIE, token_digest
from .legacy_backup import backup
from .offline_worker import clear_expired
from .platform_db import AuthSession, Base, User, database_engine, platform_session, utc_now


@pytest.fixture
def platform(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'platform.sqlite3').as_posix()}"
    monkeypatch.setenv("BASIRA_PLATFORM_DATABASE_URL", url)
    monkeypatch.setenv("BASIRA_DB_PATH", str(tmp_path / "legacy.sqlite3"))
    monkeypatch.setenv("BASIRA_ALLOW_INLINE_ANALYSIS", "1")
    engine = database_engine(url)
    Base.metadata.create_all(engine)
    tokens = ("a" * 43, "b" * 43)
    with platform_session() as db:
        for number, token in enumerate(tokens):
            user = User(issuer="https://identity.test", subject=str(number), display_name=f"User {number}")
            db.add(user)
            db.flush()
            db.add(AuthSession(token_digest=token_digest(token), user_id=user.id, created_at=utc_now(),
                               expires_at=utc_now() + timedelta(hours=1)))
    with TestClient(main.app) as first, TestClient(main.app) as second:
        first.cookies.set(SESSION_COOKIE, tokens[0])
        second.cookies.set(SESSION_COOKIE, tokens[1])
        org = first.post("/api/platform/organizations", json={"name": "Project owners"}).json()
        project = first.post(f"/api/platform/organizations/{org['id']}/projects",
                             json={"name": "Release artifacts"}).json()
        other_org = second.post("/api/platform/organizations", json={"name": "Other owners"}).json()
        assert other_org["id"] != org["id"]
        yield first, second, SimpleNamespace(org_id=org["id"], project_id=project["id"])
    engine.dispose()


def artifact(kind="html", name="release.html", content=b'<script src="http://assets.test/main.js"></script>'):
    return {"kind": kind, "name": name, "content": base64.b64encode(content).decode()}


def submit(client, ctx, data=None, key="request-123"):
    return client.post(f"/api/platform/projects/{ctx.project_id}/scans",
                       json=data or artifact(), headers={"Idempotency-Key": key})


def test_project_job_delivery_report_recovery_and_scope(platform):
    owner, stranger, ctx = platform
    root = f"/api/platform/projects/{ctx.project_id}"
    created = submit(owner, ctx)
    assert created.status_code == 202, created.text
    scan_id = created.json()["id"]
    assert submit(owner, ctx).json()["id"] == scan_id
    assert submit(owner, ctx, artifact(content=b"<p>other</p>")).status_code == 409
    assert submit(stranger, ctx).status_code == 404

    delivered = []
    def broken_broker(*ids):
        raise RuntimeError("broker offline")
    with pytest.raises(RuntimeError, match="broker offline"):
        jobs.dispatch_once(broken_broker)
    assert jobs.dispatch_once(lambda *ids: delivered.append(ids))
    assert delivered == [(ctx.org_id, ctx.project_id, scan_id)]

    claimed = store.claim(*delivered[0])
    assert store.claim(*delivered[0]) is None
    assert store.reserve_enrichment(*delivered[0], claimed["lease"])
    assert not store.reserve_enrichment(*delivered[0], claimed["lease"])
    assert not store.record_stage(*delivered[0], "wrong-lease", "stage_start", "model")
    with pytest.raises(ValueError):
        store.record_stage(*delivered[0], claimed["lease"], "completed", "model")
    assert store.record_stage(*delivered[0], claimed["lease"], "stage_start", "model")
    with platform_session() as db:
        db.execute(store.scans.update().where(store.scans.c.id == scan_id)
                   .values(lease_until=store.now() - timedelta(seconds=1)))
    jobs.execute_scan(*delivered[0])
    assert not store.finish(*delivered[0], claimed["lease"], message="stale")
    jobs.execute_scan(*delivered[0])
    after = owner.get(root + "/scans/" + scan_id, params={"after": 1}).json()
    assert after["state"] == "completed", after
    assert after["attempt"] == 2
    assert [row["kind"] for row in after["events"]] == ["running", "stage_start", "running", *["agent_start"] * 5, *["agent_done"] * 5, "completed"]
    assert [row["sequence"] for row in after["events"]] == list(range(2, 16))
    report = owner.get(root + "/reports/" + scan_id).json()
    assert len(report["coverage"]) == 114
    assert {step["role"] for step in report["steps"] if step["status"] == "done"} == {
        "orchestrator", "planning", "analysis", "validation", "reporting",
    }
    assert {item["rule"] for item in report["findings"]} == {"http-script"}
    assert report["findings"][0]["path"] == "release.html"
    assert "assets.test" not in json.dumps(report)
    assert owner.get(root + "/reports/" + scan_id + "/download?format=json").json() == report
    assert stranger.get(root + "/reports/" + scan_id).status_code == 404
    assert stranger.get(root + "/scans/" + scan_id).status_code == 404
    assert len(owner.get(root + "/reports").json()["reports"]) == 1
    with platform_session() as db:
        assert db.execute(sa.select(store.scans.c.raw)).scalar_one() is None
        assert not db.execute(sa.select(store.dispatch)).all()


def test_cancel_invalid_input_policy_and_six_memory_types(platform):
    owner, stranger, ctx = platform
    root = f"/api/platform/projects/{ctx.project_id}"
    bundle = artifact("config", "settings.json", json.dumps({
        "files": {"Dockerfile": "FROM python:3\nUSER root\n"},
    }).encode())
    assert owner.put(root + "/policy", json={"allowed_kinds": ["config"],
                                            "base_url": "https://authorized.test"}).status_code == 200
    assert submit(owner, ctx).status_code == 409
    first = submit(owner, ctx, bundle).json()["id"]
    first_ids = (ctx.org_id, ctx.project_id, first)
    claim = store.claim(*first_ids)
    assert owner.post(root + "/scans/" + first + "/cancel").json()["state"] == "cancelled"
    assert not store.finish(*first_ids, claim["lease"], message="late")

    broken = submit(owner, ctx, artifact("config", "settings.json", b"{"), key="another-123").json()["id"]
    jobs.execute_scan(ctx.org_id, ctx.project_id, broken)
    assert owner.get(root + "/scans/" + broken).json()["state"] == "failed"

    note = owner.post(root + "/memory/knowledge", json={
        "title": "Container least privilege", "reference": "Maintained baseline", "note": "Review USER usage.",
    }).json()["id"]
    done = submit(owner, ctx, bundle, key="findings-123").json()["id"]
    jobs.execute_scan(ctx.org_id, ctx.project_id, done)
    memory = owner.get(root + "/memory").json()
    assert set(memory) == {"working", "episodic", "semantic", "procedural", "project", "finding"}
    assert len(memory["procedural"]["rules"]) == 114
    assert {item["rule"] for item in memory["finding"]} >= {"INF-01"}
    assert memory["semantic"][0]["id"] == note
    assert stranger.get(root + "/memory").status_code == 404
    assert owner.delete(root + "/memory/knowledge/" + note).status_code == 200
    assert owner.get(root + "/memory").json()["semantic"] == []


def test_claim_proves_anonymous_cookie_and_preserves_id(platform):
    owner, stranger, ctx = platform
    lines = owner.post("/api/run", json={"source": "<p>legacy projection</p>"}).text.splitlines()
    original = json.loads(lines[-1])["report"]
    url = f"/api/platform/projects/{ctx.project_id}/reports/{original['id']}"
    assert owner.post(url + "/claim", json={"confirm": False}).status_code == 422
    token = owner.cookies.get(main.COOKIE)
    owner.cookies.delete(main.COOKIE)
    assert owner.post(url + "/claim", json={"confirm": True}).status_code == 404
    owner.cookies.set(main.COOKIE, token)
    assert owner.post(url + "/claim", json={"confirm": True}).status_code == 201
    assert owner.post(url + "/claim", json={"confirm": True}).status_code == 201
    assert owner.get(url).json()["id"] == original["id"]
    assert stranger.get(url).status_code == 404
    with main.database() as db:
        db.execute("UPDATE sessions SET expires_at=1 WHERE owner=?", (main.owner_key(token),))
    assert owner.get("/api/reports/" + original["id"]).status_code == 404


def test_backup_and_restore_keeps_legacy_report_ids(platform, tmp_path, monkeypatch):
    owner, _, _ = platform
    old_database = tmp_path / "legacy.sqlite3"
    token, report_id = "s" * 43, "c" * 32
    data = {"id": report_id, "created_at": "2026-11-18T12:00:00+00:00", "model": "fixture",
            "summary_ar": "تقرير", "summary_en": "Report", "metrics": {}, "findings": []}
    with sqlite3.connect(old_database) as db:
        db.executescript("""
            CREATE TABLE sessions(owner TEXT PRIMARY KEY);
            CREATE TABLE reports(id TEXT PRIMARY KEY, owner TEXT NOT NULL, created_at TEXT NOT NULL,
                                 model TEXT NOT NULL, finding_count INTEGER NOT NULL, report_json TEXT NOT NULL);
        """)
        db.execute("INSERT INTO sessions VALUES (?)", (main.owner_key(token),))
        db.execute("INSERT INTO reports VALUES (?,?,?,?,?,?)",
                   (report_id, main.owner_key(token), data["created_at"], data["model"], 0, json.dumps(data)))
    recovered = tmp_path / "recovered.sqlite3"
    assert backup(old_database, recovered) == 1
    monkeypatch.setenv("BASIRA_DB_PATH", str(recovered))
    owner.cookies.set(main.COOKIE, token)
    assert owner.get("/api/reports/" + report_id).json()["id"] == report_id
    with main.database() as db:
        assert not db.execute("SELECT expires_at FROM sessions").fetchone()[0]
        assert main.active_owner(db, token, allow_legacy=False) is None
        db.execute("UPDATE legacy_session_window SET ends_at=1")
    assert owner.get("/api/reports/" + report_id).status_code == 404
    with pytest.raises(FileExistsError):
        backup(old_database, recovered)


def test_spool_sweeps_files_left_by_dead_process(tmp_path):
    stale = time.time() - 350
    for suffix in ("request", "working", "result", "tmp"):
        item = tmp_path / f"stale.{suffix}"
        item.write_text("temporary")
        os.utime(item, (stale, stale))
    fresh = tmp_path / "fresh.request"
    fresh.touch()
    clear_expired(tmp_path)
    assert list(tmp_path.iterdir()) == [fresh]


def test_adapter_failure_is_visible_in_recoverable_partial_report(platform, monkeypatch):
    from .checks import web
    owner, _, ctx = platform
    def broken(*_args):
        raise RuntimeError("Tool failed")
    monkeypatch.setattr(web, "check", broken)
    scan = submit(owner, ctx).json()["id"]
    jobs.execute_scan(ctx.org_id, ctx.project_id, scan)
    url = f"/api/platform/projects/{ctx.project_id}"
    assert owner.get(url + "/scans/" + scan).json()["state"] == "partial"
    report = owner.get(url + "/reports/" + scan).json()
    assert report["status"] == "partial"
    assert [item["rule"] for item in report["findings"]] == ["http-script"]
    assert sum(row["status"] == "error" for row in report["coverage"]) == 17


def test_repository_bounds_and_combined_coverage():
    archive = io.BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("app/web/index.html", '<form action="http://example.test/"></form>')
        zip_file.writestr("Dockerfile", "FROM python:3\nUSER 0\n")
    report = defensive_review("repository", "snapshot.zip", archive.getvalue(), {})
    assert len(report["coverage"]) == len({item["rule"] for item in report["coverage"]}) == 114
    assert statuses(report, "http-form", "INF-01") == ("matched", "matched")
    for bad_name in ("../outside.html", "directory/nested.zip", "C:/outside.html", "foo\\bar.html"):
        bad = io.BytesIO()
        with ZipFile(bad, "w") as zip_file:
            entry = ZipInfo(bad_name)
            entry.filename = bad_name
            zip_file.writestr(entry, "content")
        with pytest.raises(InputError):
            zip_texts(bad.getvalue())


def statuses(report, *rules):
    rows = {item["rule"]: item["status"] for item in report["coverage"]}
    return tuple(rows[rule] for rule in rules)


def test_gateway_keeps_raw_input_and_memory_out_of_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("BASIRA_GATEWAY_TOKEN", "token-for-testing")
    key = tmp_path / "test-gateway.key"
    key.write_text("first-fake-key", encoding="utf-8")
    monkeypatch.setenv("BASIRA_OPENROUTER_KEY_FILE", str(key))
    monkeypatch.setenv("BASIRA_OPENROUTER_KEY", "fallback-key-must-not-be-used")
    monkeypatch.setenv("BASIRA_OPENROUTER_MODEL", "test/model")
    org_id = "a" * 32
    monkeypatch.setenv("BASIRA_OPERATOR_MODEL_ORGS", org_id)
    monkeypatch.setenv("BASIRA_PROJECT_MODEL_ENABLED", "1")
    monkeypatch.setattr(model_gateway, "start_model_call", lambda _body: (None,))
    seen = []
    def provider(url, *, headers, timeout, json, trust_env):
        assert not trust_env
        assert json["max_tokens"] == 1200
        assert json["provider"]["data_collection"] == "deny"
        seen.append((url, json["messages"][-1]["content"], headers["Authorization"]))
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "choices": [{"message": {"content": '{"priority":["http-form"]}'}}],
        })
    monkeypatch.setattr(model_gateway.httpx, "post", provider)
    with TestClient(model_gateway.app) as service:
        headers = {"Authorization": "Bearer token-for-testing"}
        facts = {"connection": "openrouter-default", "model": "test/model", "counts": {"http-form": 1},
                 "org_id": org_id, "project_id": "b" * 32, "scan_id": "c" * 32,
                 "lease": "d" * 32, "generation": "operator"}
        assert service.get("/health").status_code == 401
        assert service.get("/health", headers=headers).json() == {"ready": True, "model": "test/model"}
        assert service.post("/priority", json=facts).status_code == 401
        invalid = service.post("/priority", headers=headers, json={**facts, "memory": "secret user content"})
        assert invalid.status_code == 422 and "secret user content" not in invalid.text
        assert service.post("/priority", headers=headers, json={**facts, "model": "other/model"}).status_code == 409
        for label in ("first-fake-key", "rotated-fake-key"):
            key.write_text(label, encoding="utf-8")
            assert service.post("/priority", headers=headers, json=facts).json() == {"priority": ["http-form"]}
        key.unlink()
        assert service.get("/health", headers=headers).json() == {"ready": False, "model": "test/model"}
        assert service.post("/priority", headers=headers, json=facts).status_code == 503
    assert seen == [("https://openrouter.ai/api/v1/chat/completions", '{"http-form": 1}', f"Bearer {label}")
                    for label in ("first-fake-key", "rotated-fake-key")]
