"""Redis delivery for durable PostgreSQL jobs and offline analyzer calls."""
import base64
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
import time

from celery import Celery
import sqlalchemy as sa

from . import platform_runtime as store
from .artifact_review import RULESET_VERSION
from .contracts import Report
from .model_gateway import enrich
from .offline_worker import scan_payload, write_json

broker = os.environ.get("MARSAD_REDIS_URL", "redis://127.0.0.1:6379/0")
celery_app = Celery("marsad", broker=broker)
celery_app.conf.update(task_serializer="json", accept_content=["json"], worker_prefetch_multiplier=1,
                       task_acks_late=True, task_reject_on_worker_lost=True, task_ignore_result=True,
                       broker_connection_retry_on_startup=True, task_time_limit=80,
                       broker_transport_options={"visibility_timeout": 120, "socket_connect_timeout": 3,
                                                 "socket_timeout": 3})


def analyzed(row):
    identity = store.source_identity(row)
    identity.pop("input_kind")
    payload = {"kind": row["input_meta"]["kind"], "name": row["input_meta"]["name"],
               "content": base64.b64encode(row["raw"]).decode("ascii"), "policy": row["policy"],
               **identity}
    spool_dir = os.environ.get("MARSAD_ANALYSIS_SPOOL")
    if not spool_dir:
        if os.environ.get("MARSAD_ALLOW_INLINE_ANALYSIS") == "1":
            return scan_payload(payload)
        raise RuntimeError("Offline analysis worker is required")
    spool = Path(spool_dir)
    spool.mkdir(parents=True, exist_ok=True)
    request = spool / (row["lease"] + ".request")
    result = request.with_suffix(".result")
    tracked = (request, request.with_suffix(".working"), result)
    try:
        write_json(request, payload)
        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            if result.is_file():
                if result.stat().st_size > 8_000_000:
                    raise ValueError("Result exceeds the protocol limit")
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
            result = analyzed(row)
            if "error" in result:
                store.finish(org_id, project_id, scan_id, row["lease"], message=result["error"])
                return
            data = store.save_analysis_checkpoint(org_id, project_id, scan_id, row["lease"], result["result"])
            if data is None:
                return
        connection = None
        if row["input_meta"].get("model_connection") and data["findings"]:
            if os.environ.get("MARSAD_GATEWAY_URL") and os.environ.get("MARSAD_GATEWAY_TOKEN"):
                connection = store.reserve_model_connection(org_id, project_id, scan_id, row["lease"])
            if connection:
                enrich(data, connection, org_id=org_id, project_id=project_id, scan_id=scan_id,
                       lease=row["lease"], execution_advice=True)
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


@celery_app.task(name="marsad.scan")
def scan_task(org_id, project_id, scan_id):
    execute_scan(org_id, project_id, scan_id)


def dispatch_once(deliver=None):
    if deliver is None:
        deliver = scan_task.delay
    with store.platform_session() as db:
        due = db.execute(sa.select(store.dispatch).where(store.dispatch.c.available_at <= store.now())
                         .order_by(store.dispatch.c.available_at).limit(1)
                         .with_for_update(skip_locked=True)).mappings().first()
        if not due:
            return False
        deliver(due["org_id"], due["project_id"], due["scan_id"])
        # Retain the outbox until a terminal DB transaction commits; duplicate delivery is safe.
        db.execute(store.dispatch.update().where(store.dispatch.c.scan_id == due["scan_id"])
                   .values(available_at=store.now() + timedelta(seconds=100)))
    return True


def dispatcher():
    next_cleanup = 0
    while True:
        try:
            if time.monotonic() >= next_cleanup:
                next_cleanup = time.monotonic() + 30
                store.expire_pending_artifacts()
            if dispatch_once():
                continue
        except Exception:
            print("Task delivery unavailable; retrying.", file=sys.stderr)
        time.sleep(1)


if __name__ == "__main__":
    dispatcher()
