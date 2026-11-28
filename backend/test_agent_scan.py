import io
import json
import zipfile

import httpx
import sqlalchemy as sa

from . import agent_scan, hunter_loop, platform_jobs as jobs, platform_runtime as store
from .agent_memory import agent_runs
from .platform_db import platform_session
from .scan_events import MESSAGES
from .test_platform_runtime import artifact, platform, submit  # noqa: F401  (fixture and helper)

CONNECTION = {"id": "openrouter-default", "model": "m/free", "generation": "e" * 32, "provider": "openrouter"}


def queue(owner, ctx, key, mode):
    scan = submit(owner, ctx, key=key).json()["id"]
    with platform_session() as db:
        row = store.select_scan(db, ctx.org_id, ctx.project_id, scan)
        db.execute(store.scans.update().where(store.scans.c.id == scan).values(
            input_meta={**row["input_meta"], "mode_effective": mode, "analysis_mode": mode}))
    return scan


def runs(scan):
    with platform_session() as db:
        return db.execute(sa.select(agent_runs).where(agent_runs.c.scan_id == scan)).mappings().all()


def state(ctx, scan):
    with platform_session() as db:
        return dict(store.select_scan(db, ctx.org_id, ctx.project_id, scan))


def fail_hunter(monkeypatch):
    monkeypatch.setenv("BASIRA_AGENT_LOOP", "1")
    monkeypatch.setattr(store, "reserve_model_connection", lambda *a: CONNECTION)
    monkeypatch.setattr(agent_scan, "run_hunter", lambda *a, **k: hunter_loop.HunterResult("model_error", [], []))


def test_agents_scan_fails_loudly_when_the_hunter_fails(platform, monkeypatch):
    owner, _other, ctx = platform
    scan = queue(owner, ctx, "agent-fail-1", "agents")
    fail_hunter(monkeypatch)
    jobs.execute_scan(ctx.org_id, ctx.project_id, scan)
    assert state(ctx, scan)["state"] == "failed"
    with platform_session() as db:
        events = db.execute(sa.select(store.events.c.detail).where(store.events.c.scan_id == scan)).scalars().all()
    assert MESSAGES["scan.agent_failed"] in events


def test_hybrid_scan_keeps_the_rules_result_when_the_hunter_fails(platform, monkeypatch):
    owner, _other, ctx = platform
    scan = queue(owner, ctx, "agent-fail-2", "hybrid")
    fail_hunter(monkeypatch)
    jobs.execute_scan(ctx.org_id, ctx.project_id, scan)
    assert state(ctx, scan)["state"] == "completed"


def test_flag_off_never_reaches_the_hunter(platform, monkeypatch):
    owner, _other, ctx = platform
    scan = queue(owner, ctx, "agent-off-1", "agents")
    monkeypatch.delenv("BASIRA_AGENT_LOOP", raising=False)
    monkeypatch.setattr(agent_scan, "run_hunter", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    jobs.execute_scan(ctx.org_id, ctx.project_id, scan)
    assert state(ctx, scan)["state"] == "completed"


def zipped(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return out.getvalue()


def test_run_hunter_goes_through_the_gateway_and_records_one_run(platform, monkeypatch):
    owner, _other, ctx = platform
    scan = queue(owner, ctx, "agent-run-1", "hybrid")
    claimed = store.claim(ctx.org_id, ctx.project_id, scan)
    row = {**claimed, "raw": zipped({"app.py": "import os\nos.system(input())\n"}),
           "input_meta": {**claimed["input_meta"], "kind": "repository"}}
    monkeypatch.setenv("BASIRA_AGENT_LOOP", "1")
    monkeypatch.setenv("BASIRA_GATEWAY_URL", "http://gw")
    monkeypatch.setenv("BASIRA_GATEWAY_TOKEN", "t")
    sent = []

    def post(url, json=None, **kwargs):
        sent.append(json)
        text = '{"candidates":[{"path":"app.py","line":2,"quote":"os.system(input())"}]}'
        return httpx.Response(200, json={"content": text, "usage": {"input": 7, "output": 3}},
                              request=httpx.Request("POST", url))

    result = agent_scan.run_hunter(row, CONNECTION, "hybrid", post=post)
    assert result.status == "ok" and len(sent) == 1 and sent[0]["scan_id"] == scan
    saved = runs(scan)
    assert len(saved) == 1 and saved[0]["status"] == "completed" and saved[0]["tokens_in"] == 7
    assert saved[0]["analysis_mode"] == "hybrid" and saved[0]["reason_code"] is None


def test_run_hunter_on_a_non_repository_input_fails_without_a_call(platform, monkeypatch):
    owner, _other, ctx = platform
    scan = queue(owner, ctx, "agent-run-2", "hybrid")
    claimed = store.claim(ctx.org_id, ctx.project_id, scan)
    monkeypatch.setenv("BASIRA_AGENT_LOOP", "1")
    monkeypatch.setenv("BASIRA_GATEWAY_URL", "http://gw")
    monkeypatch.setenv("BASIRA_GATEWAY_TOKEN", "t")
    row = {**claimed, "input_meta": {**claimed["input_meta"], "kind": "html"}}
    assert agent_scan.run_hunter(row, CONNECTION, "hybrid", post=lambda *a, **k: 1 / 0).status == "model_error"
