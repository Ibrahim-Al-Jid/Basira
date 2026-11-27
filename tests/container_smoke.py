"""Smoke test against an isolated Compose project, via docker compose exec -T app python -."""
import base64
from datetime import timedelta
import json
import os
import secrets
import sys
import time
from uuid import uuid4

import httpx
import sqlalchemy as sa

from backend import platform_runtime as store
from backend.identity import SESSION_COOKIE, token_digest
from backend.platform_db import AuthSession, User, bind_project, platform_session, utc_now

BASE = "http://127.0.0.1:8000"


def seed():
    token = secrets.token_urlsafe(32)
    with platform_session() as db:
        user = User(display_name="Isolated acceptance account", issuer="https://qa.example.test", subject=uuid4().hex)
        db.add(user)
        db.flush()
        db.add(AuthSession(token_digest=token_digest(token), user_id=user.id, created_at=utc_now(),
                           expires_at=utc_now() + timedelta(minutes=10)))
    return httpx.Client(base_url=BASE, timeout=10, cookies={SESSION_COOKIE: token})


def checked(response, status=200):
    assert response.status_code == status, (response.status_code, response.text[:400])
    return response.json()


def provision(client):
    org = checked(client.post("/api/platform/organizations", json={"name": "Isolated acceptance org"}), 201)["id"]
    project = checked(client.post(f"/api/platform/organizations/{org}/projects",
                                  json={"name": "Isolated acceptance project"}), 201)["id"]
    return org, project


def main():
    with seed() as owner, seed() as other:
        org, project = provision(owner)
        other_org, other_project = provision(other)
        path = f"/api/platform/projects/{project}"
        checked(owner.put(path + "/policy", json={
            "allowed_kinds": ["config"], "base_url": "https://artifact.example.test",
        }))
        secret = "sk_" + "test_" + "a0B9c8D7e6F5g4H3i2J1k0L9"
        source = json.dumps({"files": {
            "Dockerfile": "FROM python:3\nUSER 0\n",
            "requirements.txt": "# Fixture dependency\nJinja2==3.1.4\n",
            "sample.py": f'# Fixture credential signature\nstripe.api_key = "{secret}"\n',
        }}).encode()
        headers = {"Idempotency-Key": uuid4().hex}
        body = {"kind": "config", "name": "settings.json", "content": base64.b64encode(source).decode()}
        scan = checked(owner.post(path + "/scans", headers=headers, json=body), 202)["id"]
        assert checked(owner.post(path + "/scans", headers=headers, json=body), 202)["id"] == scan
        for _ in range(50):
            snapshot = checked(owner.get(path + "/scans/" + scan))
            if snapshot["state"] not in {"queued", "running"}:
                break
            time.sleep(1)
        assert snapshot["state"] == "completed", snapshot
        cursor = snapshot["events"][0]["sequence"]
        resumed = checked(owner.get(path + "/scans/" + scan, params={"after": cursor}))
        assert all(event["sequence"] > cursor for event in resumed["events"])
        assert resumed["events"][-1]["kind"] == "completed"
        report = checked(owner.get(path + "/reports/" + scan))
        assert len([row for row in report["coverage"] if row["rule"] not in {"SRC-01", "SCA-01"}]) == 100
        assert {entry["rule"] for entry in report["findings"]} >= {"INF-01", "INF-02"}
        enabled = set(os.environ.get("BASIRA_SOURCE_ADAPTERS", "").split(","))
        if "gitleaks" in enabled:
            assert any(item["rule"] == "SRC-01" and item["path"] == "sample.py" and item["line"] == 2
                       for item in report["findings"])
        if "osv-scanner" in enabled:
            assert any(item["rule"] == "SCA-01" and item["path"] == "requirements.txt"
                       and item["line"] == 2 and item["advisory"]["database_date"] for item in report["findings"])
        for format in ("json", "sarif", "pdf"):
            exported = owner.get(path + f"/reports/{scan}/download?format={format}")
            assert exported.is_success and secret.encode() not in exported.content
        assert len({entry["role"] for entry in report["steps"] if entry["status"] == "done"}) == 5
        assert checked(owner.get(path + "/reports"))["reports"][0]["id"] == scan
        assert checked(owner.get(path + "/reports/" + scan + "/download?format=json")) == report
        assert other.get(path + "/reports/" + scan).status_code == 404
        assert other.get(path + "/memory").status_code == 404
        with platform_session() as db:
            role = db.execute(sa.text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user")).one()
            assert tuple(role) == (False, False)
            direct = sa.select(store.scans.c.raw).where(store.scans.c.id == scan)
            assert not db.execute(direct).all()
            bind_project(db, other_org, other_project)
            assert not db.execute(direct).all()
            bind_project(db, org, project)
            assert db.execute(direct).one()[0] is None
        print("PostgreSQL RLS, Redis/Celery delivery, offline scanner, idempotency, report and cursor verified.")


def cancel_with_paused_dispatcher():
    """Exercise the live PostgreSQL/API lease boundary with a deterministic lease."""
    with seed() as owner:
        org, project = provision(owner)
        path = f"/api/platform/projects/{project}"
        source = base64.b64encode(b"<p>Cancellation fixture</p>").decode()
        assigned = checked(owner.post(path + "/scans", headers={"Idempotency-Key": uuid4().hex},
                                      json={"kind": "html", "name": "cancel.html", "content": source}), 202)
        scan = assigned["id"]
        leased = store.claim(org, project, scan)
        assert leased is not None, "Pause the isolated dispatch service before running this scenario."
        state = checked(owner.post(f"{path}/scans/{scan}/cancel"))
        assert state["state"] == "cancelled"
        assert not store.finish(org, project, scan, leased["lease"], report={})
        resumed = checked(owner.get(f"{path}/scans/{scan}", params={"after": assigned["cursor"]}))
        assert [event["kind"] for event in resumed["events"]] == ["running", "cancelled"]
        assert owner.get(f"{path}/reports/{scan}").status_code == 404
        with platform_session() as db:
            bind_project(db, org, project)
            row = store.select_scan(db, org, project, scan)
            assert row["raw"] is None and row["report"] is None
            assert db.scalar(sa.select(store.dispatch.c.scan_id).where(store.dispatch.c.scan_id == scan)) is None
        print("PostgreSQL cancellation, cursor recovery and rejection of late publication verified.")


if __name__ == "__main__":
    if "--cancel-with-dispatcher-paused" in sys.argv:
        cancel_with_paused_dispatcher()
    else:
        main()
