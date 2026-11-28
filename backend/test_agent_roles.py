"""All five roles wired together with a scripted model: plan, fallback and failure per role, in both modes."""
import json

import pytest

from . import agent_client, agent_scan, platform_jobs as jobs, platform_runtime as store
from .contracts import AgentRun
from .hunter_loop import FLAG
from .platform_db import platform_session
from .scan_events import MESSAGES
from .test_agent_scan import CONNECTION, queue, state
from .test_platform_runtime import platform  # noqa: F401  (fixture)

import sqlalchemy as sa

FILES = {"app.py": "import os\nos.system(input())\n"}
RULE = "http-script"
ROLES = ("Maestro", "Scout", "Hunter", "Scribe")
ROW = {"org_id": "o", "project_id": "p", "id": "s", "lease": "l"}
FINDING = {"rule": "WEB-01", "severity": "high", "line": 1, "path": "app.py", "title": "t", "fingerprint": "c" * 64}


def say(payload, tokens=(10, 5)):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {"content": text, "tool_calls": [], "usage": {"input": tokens[0], "output": tokens[1]}}


def answers(**override):
    base = {
        "Maestro": say({"stages": ["scout", "hunter", "auditor", "scribe"], "hunter_steps": 4}),
        "Scout": say({"picks": ["app.py"]}),
        "Hunter": say({"candidates": [{"path": "app.py", "line": 2, "quote": "os.system(input())", "rule": RULE}]}),
        "Scribe": say({"summary_en": "The review found 1 rule findings and 1 place for human review.",
                       "summary_ar": "المراجعة لقت 1 ملاحظة ومكان واحد يحتاج مراجعة بشرية.", "cites": ["F1", "A1"]}),
    }
    base.update(override)
    return base


def scripted(monkeypatch, table, seen=None):
    def build(*args, **kwargs):
        def model(messages, tools):
            role = next(name for name in ROLES if f"You are {name}" in messages[0]["content"] or f"You are the {name}" in messages[0]["content"])
            if seen is not None:
                seen.append(role)
            reply = table[role]
            if isinstance(reply, Exception):
                raise reply
            return reply
        return model
    monkeypatch.setenv(FLAG, "1")
    monkeypatch.setattr(agent_scan, "snapshot", lambda row: FILES)
    monkeypatch.setattr(agent_scan, "gateway_config", lambda: ("http://gw", {}))
    monkeypatch.setattr(agent_client, "gateway_model", build)
    recorded = []
    monkeypatch.setattr(agent_scan, "record_run", lambda row, mode, model, result, steps, role="hunter":
                        recorded.append((role, result.status)))
    return recorded


def run(mode, monkeypatch, table, seen=None):
    recorded = scripted(monkeypatch, table, seen)
    return agent_scan.run_agents(ROW, CONNECTION, mode, [FINDING]), recorded


@pytest.mark.parametrize("mode", ["hybrid", "agents"])
def test_all_roles_run_in_order_and_each_records_a_run(monkeypatch, mode):
    seen = []
    outcome, recorded = run(mode, monkeypatch, answers(), seen)
    assert outcome.ok and seen == ["Maestro", "Scout", "Hunter", "Scribe"]
    assert [role for role, _ in recorded] == ["maestro", "scout", "hunter", "scribe"]
    assert [item["status"] for item in outcome.phases] == ["completed"] * 4
    assert outcome.agent_findings[0]["assessment"] == "review_required" and outcome.summary["source"] == "agent"
    AgentRun(status="completed", phases=outcome.phases)


def test_the_plan_can_drop_scout_and_scribe(monkeypatch):
    plan = say({"stages": ["hunter", "auditor"], "hunter_steps": 3})
    seen = []
    outcome, _ = run("hybrid", monkeypatch, answers(Maestro=plan), seen)
    assert seen == ["Maestro", "Hunter"] and outcome.summary is None
    assert [(item["role"], item["status"], item.get("reason_code")) for item in outcome.phases] == [
        ("maestro", "completed", None), ("scout", "skipped", "not_planned"), ("hunter", "completed", None),
        ("scribe", "skipped", "not_planned")]


@pytest.mark.parametrize("role,reply,reason", [
    ("Maestro", say("nope"), "invalid_output"), ("Maestro", RuntimeError("x"), "model_error"),
    ("Scout", say("nope"), "invalid_output"), ("Scout", RuntimeError("x"), "model_error"),
    ("Scribe", say("nope"), "invalid_output"), ("Scribe", say({}, tokens=(20_000, 1)), "budget_tokens"),
    ("Hunter", say("nope"), "invalid_output"),
])
def test_agents_mode_stops_on_the_first_role_that_fails(monkeypatch, role, reply, reason):
    outcome, _ = run("agents", monkeypatch, answers(**{role: reply}))
    assert not outcome.ok and outcome.reason_code == reason
    assert outcome.phases[-1]["status"] == "fell_back" and outcome.phases[-1]["role"] == role.lower()


@pytest.mark.parametrize("role,reply", [
    ("Maestro", say("nope")), ("Scout", say("nope")), ("Scribe", say("nope"))])
def test_hybrid_mode_carries_on_without_a_failed_helper(monkeypatch, role, reply):
    outcome, _ = run("hybrid", monkeypatch, answers(**{role: reply}))
    assert outcome.ok and outcome.agent_findings
    assert [item["status"] for item in outcome.phases if item["role"] == role.lower()] == ["fell_back"]
    assert (outcome.summary is None) == (role == "Scribe")


def test_hybrid_mode_drops_the_agent_result_when_the_hunter_fails(monkeypatch):
    outcome, _ = run("hybrid", monkeypatch, answers(Hunter=say("nope")))
    assert not outcome.ok and outcome.reason_code == "invalid_output"


def test_scribe_has_nothing_to_describe_and_makes_no_call(monkeypatch):
    seen = []
    recorded = scripted(monkeypatch, answers(Hunter=say({"candidates": []})), seen)
    outcome = agent_scan.run_agents(ROW, CONNECTION, "agents", [])
    assert outcome.ok and "Scribe" not in seen and outcome.phases[-1] == {
        "role": "scribe", "status": "skipped", "reason_code": "empty"}
    assert "scribe" not in [role for role, _ in recorded]


def test_one_ledger_stops_later_roles_when_the_plan_is_spent(monkeypatch):
    big = say({"stages": ["scout", "hunter", "auditor", "scribe"], "hunter_steps": 4}, tokens=(3_000, 0))
    greedy = say({"picks": ["app.py"]}, tokens=(75_000, 4_000))
    outcome, _ = run("agents", monkeypatch, answers(Maestro=big, Scout=greedy))
    assert not outcome.ok and outcome.reason_code == "budget_tokens"


def test_a_job_reports_every_phase_and_the_summary_beside_unchanged_findings(platform, monkeypatch):
    owner, _other, ctx = platform
    plain = queue(owner, ctx, "agent-roles-0", "hybrid")
    monkeypatch.delenv(FLAG, raising=False)
    jobs.execute_scan(ctx.org_id, ctx.project_id, plain)
    baseline = state(ctx, plain)["report"]["findings"]
    scan = queue(owner, ctx, "agent-roles-1", "hybrid")
    scripted(monkeypatch, answers())
    monkeypatch.setattr(store, "reserve_model_connection", lambda *a: CONNECTION)
    jobs.execute_scan(ctx.org_id, ctx.project_id, scan)
    report = state(ctx, scan)["report"]
    assert report["findings"] == baseline and report["agent_findings"]
    assert report["agent_run"]["status"] == "completed" and len(report["agent_run"]["phases"]) == 4
    assert report["agent_summary"]["source"] == "agent"


@pytest.mark.parametrize("role", ["Maestro", "Scout", "Scribe"])
def test_a_job_fails_loudly_in_agents_mode_and_falls_back_in_hybrid(platform, monkeypatch, role):
    owner, _other, ctx = platform
    scripted(monkeypatch, answers(**{role: say("nope")}))
    monkeypatch.setattr(store, "reserve_model_connection", lambda *a: CONNECTION)
    loud = queue(owner, ctx, "agent-roles-loud-" + role, "agents")
    jobs.execute_scan(ctx.org_id, ctx.project_id, loud)
    assert state(ctx, loud)["state"] == "failed"
    with platform_session() as db:
        events = db.execute(sa.select(store.events.c.detail).where(store.events.c.scan_id == loud)).scalars().all()
    assert MESSAGES["scan.agent_failed"] in events
    soft = queue(owner, ctx, "agent-roles-soft-" + role, "hybrid")
    jobs.execute_scan(ctx.org_id, ctx.project_id, soft)
    row = state(ctx, soft)
    assert row["state"] == "completed" and row["report"]["findings"]
    assert [item["status"] for item in row["report"]["agent_run"]["phases"] if item["role"] == role.lower()] == ["fell_back"]


def test_another_account_cannot_read_an_agent_report_or_its_summary(platform, monkeypatch):
    owner, other, ctx = platform
    scan = queue(owner, ctx, "agent-roles-probe", "hybrid")
    scripted(monkeypatch, answers())
    monkeypatch.setattr(store, "reserve_model_connection", lambda *a: CONNECTION)
    jobs.execute_scan(ctx.org_id, ctx.project_id, scan)
    path = f"/api/platform/projects/{ctx.project_id}"
    own = owner.get(f"{path}/reports/{scan}")
    assert own.status_code == 200 and own.json()["agent_summary"]["source"] == "agent"
    for url in (f"{path}/reports/{scan}", f"{path}/scans/{scan}", f"{path}/reports/{scan}/download?format=json"):
        assert owner.get(url).status_code == 200, url
        denied = other.get(url)
        assert denied.status_code in (403, 404), url
        assert "agent_summary" not in denied.text and "agent_findings" not in denied.text and "phases" not in denied.text
