"""One scan through the whole agent path with a scripted model: worker, gateway /chat, Hunter loop, Auditor, report.

Nothing leaves the process. The provider is a scripted function, the gateway is the real app, and the key only ever
appears in the provider call."""
import io
import json
import zipfile

import httpx
import pytest
import sqlalchemy as sa

from . import agent_client, agent_scan, model_gateway, platform_jobs as jobs, platform_runtime as store
from .agent_memory import agent_runs
from .platform_db import platform_session
from .test_model_connections import GATEWAY, IDENTIFIER, KEY, MODEL, credential_platform, project_root, setup_key  # noqa: F401
from .test_platform_runtime import artifact, platform  # noqa: F401  (fixtures)
from .test_platform_runtime import submit

SOURCE = "import os\n\ndef run(cmd):\n    os.system(cmd)\n"
RULE = sorted(agent_scan.EXTENDED_IDS)[0]


def archive():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as bundle:
        bundle.writestr("app.py", SOURCE)
        bundle.writestr("README.md", "# demo\n")
    return out.getvalue()


def wire(monkeypatch, answers, provider_calls):
    routed = httpx.post  # the fixture's router: gateway URLs go to the real gateway app

    def post(url, **kwargs):
        if url.startswith(GATEWAY):
            return routed(url, **kwargs)
        provider_calls.append((url, kwargs["headers"]["Authorization"], kwargs["json"]))
        text = answers.pop(0)
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 20, "completion_tokens": 6}})

    monkeypatch.setattr(httpx, "post", post)
    # gateway_model captured httpx.post when it was defined, so point its default at the same router.
    monkeypatch.setattr(agent_client.gateway_model, "__defaults__", (routed,))


def scan_through(client, ctx, monkeypatch, mode, answers):
    assert setup_key(client, ctx).status_code == 200
    policy = {"allowed_kinds": ["repository"], "model_connection": IDENTIFIER}
    assert client.put(project_root(ctx) + "/policy", json=policy).status_code == 200
    monkeypatch.setenv("BASIRA_AGENT_LOOP", "1")
    monkeypatch.setenv("BASIRA_GATEWAY_TOKEN", "test-only-gateway-auth")
    calls = []
    wire(monkeypatch, answers, calls)
    body = {**artifact("repository", "snapshot.zip", archive()), "scope_version": 1, "acknowledge_scope": True,
            "model_connection": IDENTIFIER, "analysis_mode": mode}
    created = submit(client, ctx, body, key="agent-e2e-" + mode)
    assert created.status_code == 202, created.text
    scan = created.json()["id"]
    jobs.execute_scan(ctx.org_id, ctx.project_id, scan)
    with platform_session() as db:
        row = dict(store.select_scan(db, ctx.org_id, ctx.project_id, scan))
        runs = db.execute(sa.select(agent_runs).where(agent_runs.c.scan_id == scan)).mappings().all()
    return row, runs, calls


def tool(name, **arguments):
    return json.dumps({"tool_calls": [{"name": name, "arguments": arguments}]})


def final(*places):
    return json.dumps({"candidates": list(places)})


GOOD = {"path": "app.py", "line": 4, "quote": "os.system(cmd)", "rule": RULE}
INVENTED = {"path": "app.py", "line": 2, "quote": "this line does not exist", "rule": RULE}


def test_hybrid_scan_goes_through_gateway_hunter_and_auditor_into_agent_findings(credential_platform, monkeypatch):
    client, _, _, ctx, _, _ = credential_platform
    answers = [tool("search_code", path="app.py", pattern="system"), tool("read_file", path="app.py"),
               final(GOOD, INVENTED)]
    row, runs, provider = scan_through(client, ctx, monkeypatch, "hybrid", answers)
    assert row["state"] in ("completed", "partial"), row.get("report")
    report = row["report"]
    assert [(item["path"], item["line"], item["rule"]) for item in report["agent_findings"]] == [("app.py", 4, RULE)]
    assert report["agent_findings"][0]["source"] == "agent" and report["agent_findings"][0]["assessment"] == "review_required"
    assert report["input_artifact"]["mode_effective"] == "hybrid"
    assert len(provider) == 3 and all(key == "Bearer " + KEY for _, key, _ in provider)
    assert all(not any(item["role"] == "tool" for item in call["messages"]) for _, _, call in provider)
    [run] = runs
    assert (run["status"], run["steps"], run["tokens_in"], run["analysis_mode"]) == ("completed", 3, 60, "hybrid")
    with platform_session() as db:
        assert db.scalar(sa.select(store.scans.c.agent_calls).where(store.scans.c.id == row["id"])) == 3


def test_hybrid_scan_keeps_the_rules_result_when_the_model_returns_garbage(credential_platform, monkeypatch):
    client, _, _, ctx, _, _ = credential_platform
    row, runs, _ = scan_through(client, ctx, monkeypatch, "hybrid", ["not json at all"])
    assert row["state"] in ("completed", "partial")
    assert "agent_findings" not in row["report"] and row["report"]["input_artifact"]["mode_effective"] == "hybrid"
    assert [(run["status"], run["reason_code"]) for run in runs] == [("failed", "invalid_output")]


def test_agents_scan_fails_loudly_when_the_model_returns_garbage(credential_platform, monkeypatch):
    client, _, _, ctx, _, _ = credential_platform
    row, runs, _ = scan_through(client, ctx, monkeypatch, "agents", ["not json at all"])
    assert row["state"] == "failed" and row["report"] is None
    assert [run["reason_code"] for run in runs] == ["invalid_output"]


def test_a_loop_that_never_finishes_stops_at_the_step_budget_and_the_gateway_cap(credential_platform, monkeypatch):
    client, _, _, ctx, _, _ = credential_platform
    forever = [tool("search_code", path="app.py", pattern="os") for _ in range(20)]
    row, runs, provider = scan_through(client, ctx, monkeypatch, "hybrid", forever)
    assert row["state"] in ("completed", "partial")
    assert len(provider) <= model_gateway.CHAT_CALL_CAP and [run["status"] for run in runs] == ["over_budget"]
