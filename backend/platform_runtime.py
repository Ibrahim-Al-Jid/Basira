"""Project runtime persistence. PostgreSQL controls leases and report publication."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from .platform_db import Base, bind_project, platform_session
from .contracts import Report, history_item


def now():
    # Store UTC as naive timestamps consistently on PostgreSQL and SQLite.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def timestamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


metadata = Base.metadata
scans = sa.Table(
    "project_scans", metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("org_id", sa.String(32), nullable=False),
    sa.Column("project_id", sa.String(32), nullable=False),
    sa.Column("user_id", sa.String(32), nullable=False),
    sa.Column("idempotency_key", sa.String(100), nullable=False),
    sa.Column("request_digest", sa.String(64), nullable=False),
    sa.Column("state", sa.String(16), nullable=False),
    sa.Column("input_meta", sa.JSON, nullable=False),
    sa.Column("raw", sa.LargeBinary),
    sa.Column("policy", sa.JSON, nullable=False),
    sa.Column("report", sa.JSON),
    sa.Column("report_index", sa.JSON),
    sa.Column("attempt", sa.Integer, nullable=False, default=0),
    sa.Column("lease", sa.String(32)),
    sa.Column("lease_until", sa.DateTime),
    sa.Column("enrichment_reserved_at", sa.DateTime),
    sa.Column("created_at", sa.DateTime, nullable=False, default=now),
    sa.Column("updated_at", sa.DateTime, nullable=False, default=now),
    sa.Column("cursor", sa.Integer, nullable=False, default=0),
    sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id")),
    sa.UniqueConstraint("org_id", "project_id", "id", name="uq_project_scans_scope"),
    sa.UniqueConstraint("org_id", "user_id", "idempotency_key", name="uq_project_scans_request"),
    sa.Index("ix_project_scans_timeline", "org_id", "project_id", "created_at"),
)
events = sa.Table(
    "project_scan_events", metadata,
    sa.Column("org_id", sa.String(32), primary_key=True),
    sa.Column("project_id", sa.String(32), primary_key=True),
    sa.Column("scan_id", sa.String(32), primary_key=True),
    sa.Column("sequence", sa.Integer, primary_key=True),
    sa.Column("kind", sa.String(24), nullable=False),
    sa.Column("detail", sa.String(350), nullable=False),
    sa.Column("occurred_at", sa.DateTime, nullable=False),
    sa.ForeignKeyConstraint(("org_id", "project_id", "scan_id"),
                            ("project_scans.org_id", "project_scans.project_id", "project_scans.id"),
                            ondelete="CASCADE"),
)
# Broker publisher only reads task addresses, never an artifact, report, or user token.
dispatch = sa.Table(
    "scan_dispatch_outbox", metadata,
    sa.Column("scan_id", sa.String(32), primary_key=True),
    sa.Column("org_id", sa.String(32), nullable=False),
    sa.Column("project_id", sa.String(32), nullable=False),
    sa.Column("available_at", sa.DateTime, nullable=False, index=True),
    sa.ForeignKeyConstraint(("org_id", "project_id", "scan_id"),
                            ("project_scans.org_id", "project_scans.project_id", "project_scans.id"),
                            ondelete="CASCADE"),
)
settings = sa.Table(
    "project_review_settings", metadata,
    sa.Column("org_id", sa.String(32), primary_key=True),
    sa.Column("project_id", sa.String(32), primary_key=True),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("policy", sa.JSON, nullable=False),
    sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id")),
)
notes = sa.Table(
    "project_knowledge", metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("org_id", sa.String(32), nullable=False),
    sa.Column("project_id", sa.String(32), nullable=False),
    sa.Column("title", sa.String(160), nullable=False),
    sa.Column("reference", sa.String(500), nullable=False),
    sa.Column("note", sa.String(2000), nullable=False),
    sa.Column("reviewer_id", sa.String(32), nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("revoked_at", sa.DateTime),
    sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id")),
    sa.Index("ix_project_knowledge_scope", "org_id", "project_id", "created_at"),
)
findings = sa.Table(
    "project_finding_observations", metadata,
    sa.Column("org_id", sa.String(32), primary_key=True),
    sa.Column("project_id", sa.String(32), primary_key=True),
    sa.Column("scan_id", sa.String(32), primary_key=True),
    sa.Column("fingerprint", sa.String(64), primary_key=True),
    sa.Column("rule", sa.String(60), nullable=False),
    sa.Column("count", sa.Integer, nullable=False),
    sa.ForeignKeyConstraint(("org_id", "project_id", "scan_id"),
                            ("project_scans.org_id", "project_scans.project_id", "project_scans.id"),
                            ondelete="CASCADE"),
    sa.Index("ix_finding_fingerprint", "org_id", "project_id", "fingerprint"),
)
legacy = sa.Table(
    "project_legacy_reports", metadata,
    sa.Column("legacy_id", sa.String(32), primary_key=True),
    sa.Column("org_id", sa.String(32), nullable=False),
    sa.Column("project_id", sa.String(32), nullable=False),
    sa.Column("user_id", sa.String(32), nullable=False),
    sa.Column("report", sa.JSON, nullable=False),
    sa.Column("report_index", sa.JSON, nullable=False),
    sa.Column("claimed_at", sa.DateTime, nullable=False),
    sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id")),
    sa.Index("ix_legacy_reports_scope", "org_id", "project_id"),
)
TENANT_TABLES = (scans, events, settings, notes, findings, legacy)
TERMINAL = {"completed", "partial", "failed", "cancelled"}
MAX_ATTEMPTS = 3


class Conflict(ValueError):
    pass


class QueueLimit(ValueError):
    pass


def scope(table, org_id, project_id):
    return sa.and_(table.c.org_id == org_id, table.c.project_id == project_id)


def select_scan(db, org_id, project_id, scan_id, *, lock=False):
    query = sa.select(scans).where(scope(scans, org_id, project_id), scans.c.id == scan_id)
    if lock:
        query = query.with_for_update()
    return db.execute(query).mappings().first()


def record(db, row, kind, detail):
    sequence = row["cursor"] + 1
    db.execute(events.insert().values(org_id=row["org_id"], project_id=row["project_id"],
                                      scan_id=row["id"], sequence=sequence, kind=kind,
                                      detail=detail, occurred_at=now()))
    return sequence


def create_scan(ctx, envelope, raw, idempotency_key):
    digest = hashlib.sha256(json.dumps(envelope, sort_keys=True).encode() + b"\x00" + raw).hexdigest()
    ids = {"org_id": ctx.org_id, "project_id": ctx.project_id}
    with platform_session() as db:
        bind_project(db, **ids)
        def find_existing():
            return db.execute(sa.select(scans).where(
                scope(scans, **ids), scans.c.user_id == ctx.user_id, scans.c.idempotency_key == idempotency_key,
            )).mappings().first()
        found = find_existing()
        if found:
            if found["request_digest"] != digest:
                raise Conflict("المفتاح ده مرتبط بطلب مختلف.")
            return scan_view(found)
        projects = metadata.tables["projects"]
        db.execute(sa.select(projects.c.id).where(projects.c.org_id == ctx.org_id,
                                                   projects.c.id == ctx.project_id).with_for_update()).one()
        found = find_existing()
        if found:
            if found["request_digest"] != digest:
                raise Conflict("المفتاح ده مرتبط بطلب مختلف.")
            return scan_view(found)
        pending = db.execute(sa.select(sa.func.count()).select_from(scans).where(
            scope(scans, **ids), scans.c.state.in_(["queued", "running"]),
        )).scalar_one()
        recent = db.execute(sa.select(sa.func.count()).select_from(scans).where(
            scope(scans, **ids), scans.c.user_id == ctx.user_id,
            scans.c.created_at > now() - timedelta(minutes=1),
        )).scalar_one()
        if pending >= 10 or recent >= 8:
            raise QueueLimit()
        policy_row = db.execute(sa.select(settings).where(scope(settings, **ids))).mappings().first()
        if not policy_row or envelope["kind"] not in policy_row["policy"].get("allowed_kinds", ["html"]):
            if envelope["kind"] != "html" or policy_row:
                raise Conflict("نوع المدخل خارج السياسة الحالية للمشروع.")
        data = {
            **ids, "id": uuid4().hex, "user_id": ctx.user_id, "state": "queued", "cursor": 0,
            "idempotency_key": idempotency_key, "request_digest": digest, "input_meta": envelope, "raw": raw,
            "policy": {"version": policy_row["version"], **policy_row["policy"]} if policy_row else {"version": 0},
            "created_at": now(), "updated_at": now(), "attempt": 0,
        }
        try:
            with db.begin_nested():
                db.execute(scans.insert().values(**data))
                db.execute(dispatch.insert().values(scan_id=data["id"], **ids, available_at=now()))
                data["cursor"] = record(db, data, "queued", "تم تسجيل الطلب للفحص.")
                db.execute(scans.update().where(scans.c.id == data["id"]).values(cursor=data["cursor"]))
        except IntegrityError:
            found = find_existing()
            if not found or found["request_digest"] != digest:
                raise Conflict("المفتاح ده مرتبط بطلب مختلف.") from None
            return scan_view(found)
        return scan_view(data)


def scan_view(row):
    return {
        "id": row["id"], "state": row["state"], "artifact": row["input_meta"], "attempt": row["attempt"],
        "cursor": row["cursor"], "created_at": timestamp(row["created_at"]),
        "updated_at": timestamp(row["updated_at"]), "report_available": row["state"] in {"completed", "partial"},
    }


def claim(org_id, project_id, scan_id):
    with platform_session() as db:
        bind_project(db, org_id, project_id)
        row = select_scan(db, org_id, project_id, scan_id, lock=True)
        if not row or row["state"] in TERMINAL or (row["lease_until"] and row["lease_until"] > now()):
            return None
        if row["attempt"] >= MAX_ATTEMPTS:
            close_scan(db, row, "failed", "وصلت المهمة للحد الأقصى لمحاولات التشغيل.")
            return None
        clock = now()
        lease = uuid4().hex
        number = row["attempt"] + 1
        cursor = record(db, row, "running", f"بدأت محاولة التنفيذ رقم {number}.")
        db.execute(scans.update().where(scans.c.id == scan_id).values(
            state="running", attempt=number, lease=lease, lease_until=clock + timedelta(seconds=90),
            updated_at=clock, cursor=cursor,
        ))
        return {**row, "lease": lease, "attempt": number}


def close_scan(db, row, state, detail, report=None):
    cursor = record(db, row, state, detail)
    summary = history_item(Report.model_validate(report)).model_dump(mode="json") if report else None
    db.execute(scans.update().where(scans.c.id == row["id"]).values(
        state=state, report=report, report_index=summary, raw=None, lease=None, lease_until=None,
        updated_at=now(), cursor=cursor,
    ))
    db.execute(dispatch.delete().where(dispatch.c.scan_id == row["id"]))
    return scan_view({**row, "state": state, "cursor": cursor, "updated_at": now()})


def finish(org_id, project_id, scan_id, lease, *, report=None, message=None):
    with platform_session() as db:
        bind_project(db, org_id, project_id)
        row = select_scan(db, org_id, project_id, scan_id, lock=True)
        if (not row or row["state"] != "running" or row["lease"] != lease or row["lease_until"] <= now()):
            return False
        if report is None:
            close_scan(db, row, "failed", message or "تعذّر تنفيذ الفحص.")
            return True
        statuses = {item["status"] for item in report["coverage"]}
        state = "partial" if statuses & {"error", "skipped"} else "completed"
        report["status"] = state
        close_scan(db, row, state, "التقرير التجريبي جاهز." if state == "partial" else "اكتمل الفحص.", report)
        from .advanced_reporting import points
        observations = points(Report.model_validate(report), row["policy"])
        if observations:
            db.execute(findings.insert(), [
                {"org_id": org_id, "project_id": project_id, "scan_id": scan_id,
                 "fingerprint": item["fingerprint"], "rule": item["rule"], "count": item["count"]}
                for item in observations.values()
            ])
        return True


def reserve_enrichment(org_id, project_id, scan_id, lease):
    """At most one paid-provider attempt per scan, even after worker loss."""
    with platform_session() as db:
        bind_project(db, org_id, project_id)
        updated = db.execute(scans.update().where(
            scope(scans, org_id, project_id), scans.c.id == scan_id, scans.c.lease == lease,
            scans.c.lease_until > now(), scans.c.state == "running", scans.c.enrichment_reserved_at.is_(None),
        ).values(enrichment_reserved_at=now()))
        return updated.rowcount == 1


def cancel(ctx, scan_id):
    with platform_session() as db:
        bind_project(db, ctx.org_id, ctx.project_id)
        row = select_scan(db, ctx.org_id, ctx.project_id, scan_id, lock=True)
        if not row:
            return None
        if row["state"] in TERMINAL:
            return scan_view(row)
        return close_scan(db, row, "cancelled", "اتلغى الفحص.")


def scan_status(ctx, scan_id, after):
    with platform_session() as db:
        bind_project(db, ctx.org_id, ctx.project_id)
        row = select_scan(db, ctx.org_id, ctx.project_id, scan_id)
        if not row:
            return None
        entries = db.execute(sa.select(events).where(
            scope(events, ctx.org_id, ctx.project_id), events.c.scan_id == scan_id,
            events.c.sequence > after, events.c.sequence <= row["cursor"],
        ).order_by(events.c.sequence).limit(100)).mappings()
        return {**scan_view(row), "events": [
            {**item, "occurred_at": timestamp(item["occurred_at"])} for item in entries
        ]}
