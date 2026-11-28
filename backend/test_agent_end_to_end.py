"""One scan through the whole agent path with a scripted model: worker, gateway /chat, Maestro, Scout, Hunter loop,
Auditor, Scribe, report.

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


PLAN = json.dumps({"stages": ["scout", "hunter", "auditor", "scribe"], "hunter_steps": 6})
PICKS = json.dumps({"picks": ["app.py"]})
SUMMARY = json.dumps({"summary_en": "The review left one place for a person to check.",
                      "summary_ar": "المراجعة سابت مكان واحد محتاج حد يراجعه.", "cites": ["A1"]})


def hunter_turns(*final_places):
    return [tool("search_code", path="app.py", pattern="system"), tool("read_file", path="app.py"), final(*final_places)]


def five(hunter=None, plan=PLAN, picks=PICKS, summary=SUMMARY):
    return [plan, picks, *(hunter if hunter is not None else hunter_turns(GOOD, INVENTED)), summary]


def phases(row):
    return [(item["role"], item["status"], item.get("reason_code")) for item in row["report"]["agent_run"]["phases"]]


def test_hybrid_scan_runs_all_five_roles_through_the_gateway(credential_platform, monkeypatch):
    client, _, _, ctx, _, _ = credential_platform
    row, runs, provider = scan_through(client, ctx, monkeypatch, "hybrid", five())
    assert row["state"] in ("completed", "partial"), row.get("report")
    report = row["report"]
    assert [(item["path"], item["line"], item["rule"]) for item in report["agent_findings"]] == [("app.py", 4, RULE)]
    assert report["agent_findings"][0]["source"] == "agent" and report["agent_findings"][0]["assessment"] == "review_required"
    assert report["agent_summary"]["source"] == "agent" and report["agent_summary"]["cited"]
    assert report["agent_run"]["status"] == "completed"
    assert phases(row) == [("maestro", "completed", None), ("scout", "completed", None),
                           ("hunter", "completed", None), ("scribe", "completed", None)]
    assert report["input_artifact"]["mode_effective"] == "hybrid"
    assert len(provider) == 6 and all(key == "Bearer " + KEY for _, key, _ in provider)
    assert all(not any(item["role"] == "tool" for item in call["messages"]) for _, _, call in provider)
    assert sorted((run["role_id"], run["status"]) for run in runs) == [
        ("analysis", "completed"), ("orchestrator", "completed"), ("planning", "completed"),
        ("reporting", "completed")]
    assert sum(run["tokens_in"] for run in runs) == 120
    with platform_session() as db:
        assert db.scalar(sa.select(store.scans.c.agent_calls).where(store.scans.c.id == row["id"])) == 6
    # Model output never reaches the frozen rules findings.
    assert all(item.get("source") != "agent" for item in report["findings"])


def test_agents_scan_runs_all_five_roles_too(credential_platform, monkeypatch):
    client, _, _, ctx, _, _ = credential_platform
    row, runs, _ = scan_through(client, ctx, monkeypatch, "agents", five())
    assert row["state"] in ("completed", "partial") and row["report"]["agent_run"]["status"] == "completed"
    assert len(runs) == 4 and row["report"]["input_artifact"]["mode_effective"] == "agents"


@pytest.mark.parametrize("broken,role", [(0, "maestro"), (1, "scout"), (5, "scribe")])
def test_hybrid_scan_carries_on_when_a_helper_role_returns_garbage(credential_platform, monkeypatch, broken, role):
    client, _, _, ctx, _, _ = credential_platform
    script = five()
    script[broken] = "not json at all"
    row, runs, _ = scan_through(client, ctx, monkeypatch, "hybrid", script)
    assert row["state"] in ("completed", "partial") and row["report"]["agent_findings"]
    assert dict((name, status) for name, status, _ in phases(row))[role] == "fell_back"
    assert ("agent_summary" in row["report"]) == (role != "scribe")
    assert [run["status"] for run in runs if run["status"] == "failed"] == ["failed"]


@pytest.mark.parametrize("broken,role", [(0, "orchestrator"), (1, "planning"), (5, "reporting")])
def test_agents_scan_fails_loudly_when_any_role_returns_garbage(credential_platform, monkeypatch, broken, role):
    client, _, _, ctx, _, _ = credential_platform
    script = five()
    script[broken] = "not json at all"
    row, runs, _ = scan_through(client, ctx, monkeypatch, "agents", script)
    assert row["state"] == "failed" and row["report"] is None
    assert [(run["role_id"], run["reason_code"]) for run in runs if run["status"] == "failed"] == [(role, "invalid_output")]


def test_hybrid_scan_keeps_the_rules_result_when_the_hunter_returns_garbage(credential_platform, monkeypatch):
    client, _, _, ctx, _, _ = credential_platform
    row, runs, _ = scan_through(client, ctx, monkeypatch, "hybrid", five(hunter=["not json at all"]))
    assert row["state"] in ("completed", "partial")
    assert "agent_findings" not in row["report"] and "agent_summary" not in row["report"]
    assert row["report"]["agent_run"]["status"] == "fell_back" and row["report"]["agent_run"]["reason_code"] == "invalid_output"
    assert [(run["role_id"], run["status"]) for run in runs if run["status"] == "failed"] == [("analysis", "failed")]


def test_agents_scan_fails_loudly_when_the_hunter_returns_garbage(credential_platform, monkeypatch):
    client, _, _, ctx, _, _ = credential_platform
    row, runs, _ = scan_through(client, ctx, monkeypatch, "agents", five(hunter=["not json at all"]))
    assert row["state"] == "failed" and row["report"] is None
    assert [run["reason_code"] for run in runs if run["status"] == "failed"] == ["invalid_output"]


def test_a_loop_that_never_finishes_stops_at_the_step_budget_and_the_gateway_cap(credential_platform, monkeypatch):
    client, _, _, ctx, _, _ = credential_platform
    forever = [tool("search_code", path="app.py", pattern="os") for _ in range(20)]
    row, runs, provider = scan_through(client, ctx, monkeypatch, "hybrid", [PLAN, PICKS, *forever])
    assert row["state"] in ("completed", "partial")
    assert len(provider) <= model_gateway.CHAT_CALL_CAP
    assert [run["status"] for run in runs if run["role_id"] == "analysis"] == ["over_budget"]
