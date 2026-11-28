"""Redis delivery for durable PostgreSQL jobs and offline analyzer calls."""
import base64
import json
import os
from pathlib import Path
import sys
import time

from celery import Celery

from . import model_budget, platform_runtime as store
from .artifact_review import RULESET_VERSION
from .contracts import Report
from .model_gateway import enrich
from .offline_worker import scan_payload, write_json

broker = os.environ.get("BASIRA_REDIS_URL", "redis://127.0.0.1:6379/0")
celery_app = Celery("basira", broker=broker)
celery_app.conf.update(task_serializer="json", accept_content=["json"], worker_prefetch_multiplier=1,
                       task_acks_late=True, task_reject_on_worker_lost=True, task_ignore_result=True,
                       broker_connection_retry_on_startup=True, task_time_limit=80,
                       broker_transport_options={"visibility_timeout": 120, "socket_connect_timeout": 3,
                                                 "socket_timeout": 3})


LIVE_ROLES = {"orchestrator", "planning", "analysis", "validation", "reporting"}


def analyzed(row, on_start=None):
    identity = store.source_identity(row)
    identity.pop("input_kind")
    payload = {"kind": row["input_meta"]["kind"], "name": row["input_meta"]["name"],
               "content": base64.b64encode(row["raw"]).decode("ascii"), "policy": row["policy"],
               **identity}
    spool_dir = os.environ.get("BASIRA_ANALYSIS_SPOOL")
    if not spool_dir:
        if os.environ.get("BASIRA_ALLOW_INLINE_ANALYSIS") == "1":
            return scan_payload(payload, progress=on_start)
        raise RuntimeError("Offline analysis worker is required")
    spool = Path(spool_dir)
    spool.mkdir(parents=True, exist_ok=True)
    request = spool / (row["lease"] + ".request")
    result = request.with_suffix(".result")
    marks = request.with_suffix(".progress")
    tracked = (request, request.with_suffix(".working"), result, marks)
    seen = 0

    def announce():
        nonlocal seen
        if on_start is None or not marks.is_file():
            return
        try:
            lines = marks.read_text(encoding="ascii").splitlines()
        except (OSError, ValueError):
            return
        for role in lines[seen:]:
            if role in LIVE_ROLES:
                on_start(role)
        seen = len(lines)
    try:
        write_json(request, payload)
        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            announce()
            if result.is_file():
                if result.stat().st_size > 8_000_000:
                    raise ValueError("Result exceeds the protocol limit")
                announce()
                return json.loads(result.read_text(encoding="utf-8"))
            time.sleep(0.25)
        raise TimeoutError("The scanner did not return a result")
    finally:
        for path in tracked:
            path.unlink(missing_ok=True)


def execute_scan(org_id, project_id, scan_id):
    row = store.claim(org_id, project_id, scan_id)
    if row is None:
        return
    try:
        data = row["analysis_checkpoint"]
        if data is None:
            result = analyzed(row, lambda role: store.record_stage(
                org_id, project_id, scan_id, row["lease"], "agent_start", role))
            if "error" in result:
                store.finish(org_id, project_id, scan_id, row["lease"], message=result["error"])
                return
            data = store.save_analysis_checkpoint(org_id, project_id, scan_id, row["lease"], result["result"])
            if data is None:
                return
        connection = None
        if row["input_meta"].get("model_connection") and data["findings"]:
            if os.environ.get("BASIRA_GATEWAY_URL") and os.environ.get("BASIRA_GATEWAY_TOKEN"):
                verdict = model_budget.decide(
                    model_budget.daily_limit(row["input_meta"].get("connection_model")),
                    store.model_requests_today(org_id, project_id))
                if verdict["allowed"]:
                    connection = store.reserve_model_connection(org_id, project_id, scan_id, row["lease"])
                else:
                    store.record_stage(org_id, project_id, scan_id, row["lease"], "model_skipped", verdict["reason_ar"])
                    data["enrichment"] = "fallback"
            if connection:
                store.record_stage(org_id, project_id, scan_id, row["lease"], "stage_start", "model")
                began = time.monotonic()
                enrich(data, connection, org_id=org_id, project_id=project_id, scan_id=scan_id,
                       lease=row["lease"], execution_advice=True)
                outcome = connection.get("provider", "openrouter") if data.get("enrichment") == "model" else "fallback"
                store.record_stage(org_id, project_id, scan_id, row["lease"], "agent_done",
                                   f"model|{round((time.monotonic() - began) * 1000)}|{outcome}")
            elif row["enrichment_started_at"] is not None:
                data["enrichment"] = "fallback"
                data["metrics"]["modelCalls"] = 1
            else:
                data["enrichment"] = "fallback"
        review = Report.model_validate({
            **data, "schema_version": 2, "id": scan_id, "created_at": store.timestamp(store.now()),
            "model": connection["model"] if connection and data.get("enrichment") == "model" else None,
            "input_artifact": row["input_meta"],
            "policy_version": row["policy"]["version"], "ruleset_version": RULESET_VERSION,
        })
        report = review.model_dump(mode="json")
        if review.execution and review.findings:
            from .scan_memory import restore_review_context
            context = restore_review_context(org_id, project_id, scan_id, row["lease"], review)
            if context:
                report["review_context"] = context
    except (OSError, ValueError, KeyError, RuntimeError):
        # Leave the lease and outbox in place for another bounded attempt.
        return
    store.finish(org_id, project_id, scan_id, row["lease"], report=report)


@celery_app.task(name="basira.scan")
def scan_task(org_id, project_id, scan_id):
    execute_scan(org_id, project_id, scan_id)


def dispatch_once(deliver=None):
    if deliver is None:
        deliver = scan_task.delay
    with store.platform_session() as db:
        # Retain the outbox until a terminal DB transaction commits; duplicate delivery is safe.
        due = store.claim_dispatch(db)
        if not due:
            return False
        target = (due["org_id"], due["project_id"], due["scan_id"])
    # Deliver after the claim commits. A delivery can run the task inline (eager mode, tests,
    # single-process deployments), and that task writes to the same database: delivering
    # inside the claim transaction deadlocks the writer on SQLite.
    try:
        deliver(*target)
    except Exception:
        with store.platform_session() as db:
            store.release_dispatch(db, target[2])
        raise
    return True


def dispatcher():
    next_cleanup = 0
    while True:
        try:
            if time.monotonic() >= next_cleanup:
                next_cleanup = time.monotonic() + 30
                store.expire_pending_artifacts()
                store.purge_expired_rows()
            if dispatch_once():
                continue
        except Exception:
            print("Task delivery unavailable; retrying.", file=sys.stderr)
        time.sleep(1)


if __name__ == "__main__":
    dispatcher()
