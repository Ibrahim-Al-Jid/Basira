"""Run the Hunter for one scan inside the worker and keep its audit row (docs/ARCHITECTURE-agents.md, 7a).

The worker holds no provider key: every turn goes to the gateway through backend/agent_client.py. The result is the
Hunter's verified candidates and a fixed status code. Nothing here changes the report; the caller decides what a
failed or disabled run means for the scan mode."""
import hashlib
from uuid import uuid4

from dataclasses import dataclass, field

from . import agent_client, hunter_loop, maestro, platform_runtime as store, scout as scout_agent, scribe
from .agent_memory import agent_runs
from .artifact_review import EXTENDED_IDS, InputError, redact_label, zip_texts
from .contracts import AgentFinding
from .model_connections import gateway_config
from .platform_db import bind_job_project, platform_session
from .project_map import project_map
from .rules import RULES
from .scan_contracts import json_digest
from .source_adapters import SOURCE_TOOLS

KNOWN_RULES = frozenset(EXTENDED_IDS) | RULES.keys() | {tool.rule for tool in SOURCE_TOOLS}

RUN_STATUS = {"ok": "completed", "disabled": "skipped", "empty": "skipped", "model_error": "failed",
              "invalid_output": "failed"}
# Stored role ids (agent_roles.py) for the roles that make their own model calls. The Auditor runs inside the Hunter.
ROLE_ID = {"maestro": "orchestrator", "scout": "planning", "hunter": "analysis", "scribe": "reporting"}


def snapshot(row):
    """path -> text for a repository upload, or None when the input is not one."""
    if row["input_meta"].get("kind") != "repository":
        return None
    try:
        files = zip_texts(row["raw"])
    except InputError:
        return None
    return files or None


def identity(row, connection):
    fields = {"connection": connection["id"], "model": connection["model"], "org_id": row["org_id"],
              "project_id": row["project_id"], "scan_id": row["id"], "lease": row["lease"],
              "generation": connection["generation"]}
    if connection.get("provider", "openrouter") != "openrouter":
        fields.update(provider=connection["provider"], base_url=connection.get("base_url"))
    if connection.get("source") == "account":
        fields["source"] = "account"
    return fields


def record_run(row, mode, model, result, max_steps, role="hunter"):
    """One scan_agent_runs row per role run. Only the current lease holder may write it."""
    clock = store.now()
    with platform_session() as db:
        if not bind_job_project(db, row["org_id"], row["project_id"]):
            return False
        current = store.select_scan(db, row["org_id"], row["project_id"], row["id"], lock=True)
        if not current or current["state"] != "running" or current["lease"] != row["lease"]:
            return False
        db.execute(agent_runs.insert().values(
            id=uuid4().hex, org_id=row["org_id"], project_id=row["project_id"], scan_id=row["id"],
            role_id=ROLE_ID[role], analysis_mode=mode, model=model[:80], budget_steps=max_steps,
            status=RUN_STATUS.get(result.status, "over_budget"), steps=result.steps,
            tokens_in=result.tokens_in, tokens_out=result.tokens_out,
            reason_code=None if result.status == "ok" else result.status, started_at=clock, ended_at=clock))
        return True


def source_digest(files):
    return hashlib.sha256("\0".join(f"{path}\0{files[path]}" for path in sorted(files)).encode()).hexdigest()


def run_hunter(row, connection, mode, *, post=None, model=None, focus=(), budget=None):
    """mode is the effective mode of the scan ("agents" or "hybrid"). Returns a HunterResult."""
    files = snapshot(row)
    url, headers = gateway_config()
    if files is None or not url:
        return hunter_loop.HunterResult("model_error", [], [])
    model = model or agent_client.gateway_model(url, headers, identity(row, connection),
                                                **({"post": post} if post else {}))
    budget = budget or hunter_loop.Budget()
    result = hunter_loop.hunt(model, files, project_map(files, source_digest(files)), mode=mode, budget=budget,
                              rules=KNOWN_RULES, focus=focus)
    record_run(row, mode, connection["model"], result, budget.max_steps)
    return result


@dataclass
class AgentOutcome:
    """What the five-agent path produced. `reason_code` is set when it did not finish: an agents scan fails on it,
    a hybrid scan keeps the rules result. `phases` is the per-role account that goes into report.agent_run."""
    ok: bool
    reason_code: str | None = None
    agent_findings: list = field(default_factory=list)
    summary: dict | None = None
    phases: list = field(default_factory=list)


def run_agents(row, connection, mode, findings, *, post=None):
    """Maestro plans, Scout ranks files, the Hunter proposes candidates and the Auditor checks them, Scribe writes the
    summary of the frozen rules findings plus the accepted candidates. One ledger is charged by every role.

    agents mode: the first role that does not finish ends the run with its status. hybrid mode: Maestro falls back to
    the default plan, Scout to no focus and Scribe to no summary; only a Hunter failure drops the agent result."""
    files = snapshot(row)
    url, headers = gateway_config()
    if files is None or not url:
        return AgentOutcome(False, "model_error")
    model = agent_client.gateway_model(url, headers, identity(row, connection), **({"post": post} if post else {}))
    digest_map = project_map(files, source_digest(files))
    strict = mode == "agents"
    phases = []

    def phase(role, status, reason=None):
        phases.append({"role": role, "status": status, **({"reason_code": reason} if reason else {})})

    def fail(role, reason):
        phase(role, "fell_back", reason)
        return AgentOutcome(False, reason, phases=phases)

    planned = maestro.plan_run(model, mode, digest_map, len(files))
    ledger = maestro.Ledger(planned.plan.token_ceiling)
    ledger.charge(planned.tokens_in, planned.tokens_out)
    record_run(row, mode, connection["model"], planned, 1, "maestro")
    if planned.status != "ok":
        if strict:
            return fail("maestro", planned.status)
        phase("maestro", "fell_back", planned.status)
    else:
        phase("maestro", "completed")
    plan = planned.plan

    focus = ()
    if "scout" not in plan.stages:
        phase("scout", "skipped", "not_planned")
    else:
        picked = scout_agent.scout(model, files, digest_map, budget=scout_agent.Budget(
            max_tokens=min(scout_agent.Budget().max_tokens, ledger.remaining)))
        ledger.charge(picked.tokens_in, picked.tokens_out)
        record_run(row, mode, connection["model"], picked, 1, "scout")
        if picked.status != "ok":
            if strict:
                return fail("scout", picked.status)
            phase("scout", "fell_back", picked.status)
        else:
            phase("scout", "completed")
            focus = tuple(picked.picks)

    hunted = run_hunter(row, connection, mode, model=model, focus=focus,
                        budget=maestro.hunter_budget(plan, ledger))
    ledger.charge(hunted.tokens_in, hunted.tokens_out)
    if hunted.status != "ok":
        return fail("hunter", hunted.status)
    phase("hunter", "completed")
    accepted = agent_findings(hunted.candidates, findings)

    summary = None
    if "scribe" not in plan.stages:
        phase("scribe", "skipped", "not_planned")
    else:
        written = scribe.write_summary(model, findings, accepted, budget=scribe.Budget(
            max_tokens=min(scribe.Budget().max_tokens, ledger.remaining)))
        ledger.charge(written.tokens_in, written.tokens_out)
        if written.status == "empty":
            phase("scribe", "skipped", "empty")
        else:
            record_run(row, mode, connection["model"], written, 1, "scribe")
            if written.status != "ok":
                if strict:
                    return fail("scribe", written.status)
                phase("scribe", "fell_back", written.status)
            else:
                phase("scribe", "completed")
                summary = written.summary
    return AgentOutcome(True, agent_findings=accepted, summary=summary, phases=phases)


def agent_findings(candidates, findings):
    """Accepted Hunter candidates as report entries. A place the rules already reported is not repeated.
    The quote is redacted like every label, and the fingerprint covers rule, path and line only."""
    known = {(item.get("path"), item["line"], item["rule"]) for item in findings}
    result = []
    for item in candidates:
        path = redact_label(item["path"])
        if (path, item["line"], item["rule"]) in known:
            continue
        quote = " ".join(redact_label(item["quote"]).split())
        result.append(AgentFinding(rule=item["rule"], path=path, line=item["line"], quote=quote,
                                   fingerprint=json_digest(["agent", item["rule"], path, item["line"]])
                                   ).model_dump(mode="json"))
    return result
