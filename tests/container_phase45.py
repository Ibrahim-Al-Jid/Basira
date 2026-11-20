"""Smoke test against an isolated Compose project, via docker compose exec -T app python -."""
import base64
from datetime import timedelta
import json
import secrets
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
        source = json.dumps({"files": {"Dockerfile": "FROM python:3\nUSER 0\n"}}).encode()
        headers = {"Idempotency-Key": uuid4().hex}
        body = {"kind": "config", "name": "settings.json", "content": base64.b64encode(source).decode()}
        scan = checked(owner.post(path + "/scans", headers=headers, json=body), 202)["id"]
        assert checked(owner.post(path + "/scans", headers=headers, json=body), 202)["id"] == scan
        for _ in range(30):
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
        assert len(report["coverage"]) == 100
        assert {entry["rule"] for entry in report["findings"]} >= {"INF-01", "INF-02"}
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


if __name__ == "__main__":
    main()
