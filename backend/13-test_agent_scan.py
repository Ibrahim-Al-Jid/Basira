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
    row = state(ctx, scan)
    assert row["state"] == "completed"
    assert row["report"]["agent_run"] == {"status": "fell_back", "reason_code": "model_error"}
    assert row["report"]["input_artifact"]["mode_effective"] == "hybrid" and "agent_findings" not in row["report"]


def test_hybrid_scan_says_so_when_no_model_connection_could_be_reserved(platform, monkeypatch):
    owner, _other, ctx = platform
    scan = queue(owner, ctx, "agent-fail-3", "hybrid")
    monkeypatch.setenv("BASIRA_AGENT_LOOP", "1")
    monkeypatch.setattr(store, "reserve_model_connection", lambda *a: None)
    jobs.execute_scan(ctx.org_id, ctx.project_id, scan)
    assert state(ctx, scan)["report"]["agent_run"] == {"status": "fell_back", "reason_code": "model_unavailable"}


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


def test_candidates_without_a_known_rule_are_rejected_by_the_auditor(platform, monkeypatch):
    owner, _other, ctx = platform
    scan = queue(owner, ctx, "agent-run-3", "hybrid")
    claimed = store.claim(ctx.org_id, ctx.project_id, scan)
    row = {**claimed, "raw": zipped({"app.py": "import os\nos.system(input())\n"}),
           "input_meta": {**claimed["input_meta"], "kind": "repository"}}
    monkeypatch.setenv("BASIRA_AGENT_LOOP", "1")
    monkeypatch.setenv("BASIRA_GATEWAY_URL", "http://gw")
    monkeypatch.setenv("BASIRA_GATEWAY_TOKEN", "t")
    good = {"path": "app.py", "line": 2, "quote": "os.system(input())", "rule": "http-script"}
    texts = iter([json.dumps({"candidates": [{**good, "rule": "made-up-rule"}, {**good, "rule": None}, good]})])

    def post(url, json=None, **kwargs):
        return httpx.Response(200, json={"content": next(texts), "usage": {"input": 1, "output": 1}},
                              request=httpx.Request("POST", url))

    result = agent_scan.run_hunter(row, CONNECTION, "hybrid", post=post)
    assert result.status == "ok" and [item["rule"] for item in result.candidates] == ["http-script"]
    assert sorted(item["reason"] for item in result.rejected) == ["unknown_rule", "unknown_rule"]


def test_agent_findings_are_redacted_deduplicated_and_never_rules_findings():
    secret = "sk-" + "a" * 24
    candidates = [{"path": "a.py", "line": 3, "quote": f"key =   '{secret}'", "rule": "http-script"},
                  {"path": "b.py", "line": 1, "quote": "already found", "rule": "http-script"}]
    rules = [{"path": "b.py", "line": 1, "rule": "http-script"}]
    [item] = agent_scan.agent_findings(candidates, rules)
    assert secret not in json.dumps(item) and "[redacted]" in item["quote"]
    assert item["source"] == "agent" and item["assessment"] == "review_required" and len(item["fingerprint"]) == 64
    assert agent_scan.agent_findings(candidates, rules) == [item]


def test_hybrid_scan_adds_agent_findings_beside_unchanged_rules_findings(platform, monkeypatch):
    owner, _other, ctx = platform
    plain = queue(owner, ctx, "agent-merge-0", "hybrid")
    monkeypatch.delenv("BASIRA_AGENT_LOOP", raising=False)
    jobs.execute_scan(ctx.org_id, ctx.project_id, plain)
    baseline = state(ctx, plain)["report"]
    assert "agent_findings" not in baseline and "agent_run" not in baseline
    # The column records the mode that actually ran at creation: hybrid without the agent path ran the rules.
    assert state(ctx, plain)["analysis_mode"] == "rules"

    scan = queue(owner, ctx, "agent-merge-1", "hybrid")
    monkeypatch.setenv("BASIRA_AGENT_LOOP", "1")
    monkeypatch.setattr(store, "reserve_model_connection", lambda *a: CONNECTION)
    place = {"path": "app.py", "line": 2, "quote": "os.system(input())", "rule": "http-script"}
    monkeypatch.setattr(agent_scan, "run_hunter", lambda *a, **k: hunter_loop.HunterResult("ok", [place], []))
    jobs.execute_scan(ctx.org_id, ctx.project_id, scan)
    row = state(ctx, scan)
    assert row["state"] == "completed"
    assert row["report"]["agent_findings"][0]["path"] == "app.py"
    assert row["report"]["agent_run"] == {"status": "completed"}
    assert row["report"]["findings"] == baseline["findings"]
