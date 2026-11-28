"""Run the Hunter for one scan inside the worker and keep its audit row (docs/ARCHITECTURE-agents.md, 7a).

The worker holds no provider key: every turn goes to the gateway through backend/agent_client.py. The result is the
Hunter's verified candidates and a fixed status code. Nothing here changes the report; the caller decides what a
failed or disabled run means for the scan mode."""
import hashlib
from uuid import uuid4

from . import agent_client, hunter_loop, platform_runtime as store
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

RUN_STATUS = {"ok": "completed", "disabled": "skipped", "model_error": "failed", "invalid_output": "failed"}


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


def record_run(row, mode, model, result, budget):
    """One scan_agent_runs row per Hunter run. Only the current lease holder may write it."""
    clock = store.now()
    with platform_session() as db:
        if not bind_job_project(db, row["org_id"], row["project_id"]):
            return False
        current = store.select_scan(db, row["org_id"], row["project_id"], row["id"], lock=True)
        if not current or current["state"] != "running" or current["lease"] != row["lease"]:
            return False
        db.execute(agent_runs.insert().values(
            id=uuid4().hex, org_id=row["org_id"], project_id=row["project_id"], scan_id=row["id"],
            role_id="analysis", analysis_mode=mode, model=model[:80], budget_steps=budget.max_steps,
            status=RUN_STATUS.get(result.status, "over_budget"), steps=result.steps,
            tokens_in=result.tokens_in, tokens_out=result.tokens_out,
            reason_code=None if result.status == "ok" else result.status, started_at=clock, ended_at=clock))
        return True


def run_hunter(row, connection, mode, *, post=None):
    """mode is the effective mode of the scan ("agents" or "hybrid"). Returns a HunterResult."""
    files = snapshot(row)
    url, headers = gateway_config()
    if files is None or not url:
        return hunter_loop.HunterResult("model_error", [], [])
    digest = hashlib.sha256("\0".join(f"{path}\0{files[path]}" for path in sorted(files)).encode()).hexdigest()
    model = agent_client.gateway_model(url, headers, identity(row, connection), **({"post": post} if post else {}))
    budget = hunter_loop.Budget()
    result = hunter_loop.hunt(model, files, project_map(files, digest), mode=mode, budget=budget, rules=KNOWN_RULES)
    record_run(row, mode, connection["model"], result, budget)
    return result


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
