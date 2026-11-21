"""Project runtime persistence. PostgreSQL controls leases and report publication."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from urllib.parse import urlsplit
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from .platform_db import Base, bind_project, platform_session
from .contracts import Report, history_item
from .phase9_contracts import (
    DEFAULT_INPUTS, PROFILE, RAW_RETENTION_MINUTES, Asset, FindingObservation, ScanProvenance,
    ScopeVersion, SourceSnapshot, analyzer_plan, json_digest,
)


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
    sa.Column("source_expires_at", sa.DateTime),
    sa.Column("policy", sa.JSON, nullable=False),
    sa.Column("report", sa.JSON),
    sa.Column("report_index", sa.JSON),
    sa.Column("attempt", sa.Integer, nullable=False, default=0),
    sa.Column("lease", sa.String(32)),
    sa.Column("lease_until", sa.DateTime),
    sa.Column("enrichment_reserved_at", sa.DateTime),
    sa.Column("enrichment_started_at", sa.DateTime),
    sa.Column("created_at", sa.DateTime, nullable=False, default=now),
    sa.Column("updated_at", sa.DateTime, nullable=False, default=now),
    sa.Column("cursor", sa.Integer, nullable=False, default=0),
    sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id")),
    sa.UniqueConstraint("org_id", "project_id", "id", name="uq_project_scans_scope"),
    sa.UniqueConstraint("org_id", "user_id", "idempotency_key", name="uq_project_scans_request"),
    sa.Index("ix_project_scans_timeline", "org_id", "project_id", "created_at"),
    sa.Index("ix_project_scans_source_expiry", "source_expires_at"),
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
assets = sa.Table(
    "project_assets", metadata,
    sa.Column("org_id", sa.String(32), primary_key=True),
    sa.Column("project_id", sa.String(32), primary_key=True),
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("reference_digest", sa.String(64), nullable=False),
    sa.Column("reference", sa.String(250), nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id")),
    sa.UniqueConstraint("org_id", "project_id", "reference_digest", name="uq_project_assets_reference"),
)
provenance = sa.Table(
    "project_scan_provenance", metadata,
    sa.Column("org_id", sa.String(32), primary_key=True),
    sa.Column("project_id", sa.String(32), primary_key=True),
    sa.Column("scan_id", sa.String(32), primary_key=True),
    sa.Column("asset_id", sa.String(32)),
    sa.Column("source_sha256", sa.String(64), nullable=False),
    sa.Column("scope", sa.JSON, nullable=False),
    sa.Column("tools", sa.JSON, nullable=False),
    sa.ForeignKeyConstraint(("org_id", "project_id", "scan_id"),
                            ("project_scans.org_id", "project_scans.project_id", "project_scans.id"),
                            ondelete="CASCADE"),
    sa.ForeignKeyConstraint(("org_id", "project_id", "asset_id"),
                            ("project_assets.org_id", "project_assets.project_id", "project_assets.id")),
)
evidence_records = sa.Table(
    "project_evidence_records", metadata,
    sa.Column("org_id", sa.String(32), primary_key=True),
    sa.Column("project_id", sa.String(32), primary_key=True),
    sa.Column("scan_id", sa.String(32), primary_key=True),
    sa.Column("ordinal", sa.Integer, primary_key=True),
    sa.Column("rule", sa.String(60), nullable=False),
    sa.Column("line", sa.Integer, nullable=False),
    sa.Column("path", sa.String(240)),
    sa.Column("evidence_sha256", sa.String(64), nullable=False),
    sa.ForeignKeyConstraint(("org_id", "project_id", "scan_id"),
                            ("project_scan_provenance.org_id", "project_scan_provenance.project_id",
                             "project_scan_provenance.scan_id"), ondelete="CASCADE"),
)
TENANT_TABLES = (scans, events, settings, notes, findings, legacy, assets, provenance, evidence_records)
TERMINAL = {"completed", "partial", "failed", "cancelled"}
MAX_ATTEMPTS = 3
EXPIRED_MESSAGE = "انتهت مدة الاحتفاظ بالمدخل قبل اكتمال الفحص."
INVALID_PROVENANCE_MESSAGE = "تعذّر التحقق من مصدر الفحص أو النطاق المسجّل."


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


def project_policy(db, org_id, project_id):
    row = db.execute(sa.select(settings).where(scope(settings, org_id, project_id))).mappings().first()
    return (row["version"], row["policy"]) if row else (0, {"allowed_kinds": list(DEFAULT_INPUTS)})


def lock_project(db, org_id, project_id):
    projects = metadata.tables["projects"]
    db.execute(sa.select(projects.c.id).where(projects.c.org_id == org_id,
                                               projects.c.id == project_id).with_for_update()).one()


def web_origin(ref):
    if not ref or any(ord(char) <= 32 or ord(char) == 127 or char == "\\" for char in ref):
        return None
    try:
        url = urlsplit(ref)
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username is not None or
                url.password is not None or url.query or url.fragment):
            return None
        host = url.hostname
        origin = f"{url.scheme}://{f'[{host}]' if ':' in host else host}"
        port = url.port
    except ValueError:
        return None
    if port is not None and (url.scheme, port) not in {("http", 80), ("https", 443)}:
        origin += f":{port}"
    return origin


def declared_asset(db, ids, ref, clock):
    origin = web_origin(ref)
    if not origin:
        return None
    url = urlsplit(ref)
    fingerprint = json_digest([origin, url.path.rstrip("/")])
    existing = db.execute(sa.select(assets.c.id).where(scope(assets, **ids),
                                                       assets.c.reference_digest == fingerprint)).scalar_one_or_none()
    if existing:
        return existing
    asset_id = uuid4().hex
    from .artifact_review import redact_label
    db.execute(assets.insert().values(**ids, id=asset_id, reference_digest=fingerprint,
                                     reference=redact_label(origin), created_at=clock))
    return asset_id


def create_scan(ctx, envelope, raw, idempotency_key, *, scope_version=None, model_connection=None,
                target_reference=None, before_create=None):
    from .artifact_review import RULESET_VERSION
    from .model_connections import public_connection

    request = {**envelope, "scope_version": scope_version, "model_connection": model_connection} if scope_version is not None else envelope
    if target_reference:
        request = {**request, "target_reference": target_reference}
    digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode() + b"\x00" + raw).hexdigest()
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
        lock_project(db, **ids)
        found = find_existing()
        if found:
            if found["request_digest"] != digest:
                raise Conflict("المفتاح ده مرتبط بطلب مختلف.")
            return scan_view(found)
        if before_create:
            before_create(db)
        pending = db.execute(sa.select(sa.func.count()).select_from(scans).where(
            scope(scans, **ids), scans.c.state.in_(["queued", "running"]),
        )).scalar_one()
        recent = db.execute(sa.select(sa.func.count()).select_from(scans).where(
            scope(scans, **ids), scans.c.user_id == ctx.user_id,
            scans.c.created_at > now() - timedelta(minutes=1),
        )).scalar_one()
        if pending >= 10 or recent >= 8:
            raise QueueLimit()
        version, policy = project_policy(db, **ids)
        if scope_version is not None and scope_version != version:
            raise Conflict("سياسة المشروع اتغيّرت. راجع النطاق مرة تانية قبل الفحص.")
        if envelope["kind"] not in policy.get("allowed_kinds", DEFAULT_INPUTS):
            raise Conflict("نوع المدخل خارج السياسة الحالية للمشروع.")
        if target_reference:
            configured_origin = web_origin(policy.get("base_url"))
            if configured_origin and target_reference != configured_origin:
                raise Conflict("عنوان الموقع لازم يطابق الأصل المحدد في سياسة المشروع.")
            if not configured_origin:
                policy = {**policy, "base_url": target_reference}
        if envelope["kind"] == "zap" and not web_origin(policy.get("base_url")):
            raise Conflict("تقرير ZAP يحتاج عنوان موقع مطابق للأدلة المحفوظة.")
        connection = public_connection(db, ctx.org_id, policy) if model_connection else None
        if model_connection and (not connection or model_connection != connection["id"]):
            raise Conflict("اتصال الموديل مش متاح في سياسة المشروع.")
        tools = analyzer_plan(envelope["kind"])
        if not tools:
            raise Conflict("مفيش أدوات تحليل مسجلة لنوع المدخل ده.")
        clock = now()
        scan_id = uuid4().hex
        artifact = {**envelope, "enrich": bool(connection)}
        if connection:
            artifact.update(model_connection=connection["id"], connection_model=connection["model"],
                            connection_generation=connection["generation"])
        data = {
            **ids, "id": scan_id, "user_id": ctx.user_id, "state": "queued", "cursor": 0,
            "idempotency_key": idempotency_key, "request_digest": digest, "input_meta": artifact, "raw": raw,
            "policy": {**policy, "version": version, "_analysis_plan": tools, "_ruleset_version": RULESET_VERSION},
            "source_expires_at": clock + timedelta(minutes=RAW_RETENTION_MINUTES),
            "created_at": clock, "updated_at": clock, "attempt": 0,
        }
        try:
            with db.begin_nested():
                asset_id = declared_asset(db, ids, policy.get("base_url"), clock)
                db.execute(scans.insert().values(**data))
                pinned_scope = ScopeVersion(version=version, sha256=json_digest({"version": version, **policy}),
                                            asset_id=asset_id, ruleset_version=RULESET_VERSION,
                                            asset_source="scan_reference" if target_reference else "project_policy")
                db.execute(provenance.insert().values(**ids, scan_id=scan_id, asset_id=asset_id,
                           source_sha256=hashlib.sha256(raw).hexdigest(),
                           scope=pinned_scope.model_dump(mode="json"), tools=tools))
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
    artifact = {key: value for key, value in row["input_meta"].items() if key not in {"connection_generation", "connection_model", "model_connection"}}
    return {
        "id": row["id"], "state": row["state"], "artifact": artifact, "attempt": row["attempt"],
        "cursor": row["cursor"], "created_at": timestamp(row["created_at"]),
        "updated_at": timestamp(row["updated_at"]), "report_available": row["state"] in {"completed", "partial"},
    }


def intact_input(db, row):
    policy = row["policy"]
    pinned = db.execute(sa.select(provenance.c.source_sha256, provenance.c.scope, provenance.c.tools).where(
        scope(provenance, row["org_id"], row["project_id"]), provenance.c.scan_id == row["id"],
    )).mappings().first()
    if not pinned:
        return "_analysis_plan" not in policy  # Historical queued jobs have no provenance record.
    if row["raw"] is None:
        return False
    original_policy = {key: value for key, value in policy.items() if key not in {"_analysis_plan", "_ruleset_version"}}
    return (hashlib.sha256(row["raw"]).hexdigest() == pinned["source_sha256"] and
            json_digest(original_policy) == pinned["scope"].get("sha256") and
            policy.get("_analysis_plan") == pinned["tools"] and
            policy.get("_ruleset_version") == pinned["scope"].get("ruleset_version"))


def claim(org_id, project_id, scan_id):
    with platform_session() as db:
        bind_project(db, org_id, project_id)
        row = select_scan(db, org_id, project_id, scan_id, lock=True)
        if not row or row["state"] in TERMINAL:
            return None
        if row["source_expires_at"] and row["source_expires_at"] <= now():
            close_scan(db, row, "failed", EXPIRED_MESSAGE)
            return None
        if row["lease_until"] and row["lease_until"] > now():
            return None
        if not intact_input(db, row):
            close_scan(db, row, "failed", INVALID_PROVENANCE_MESSAGE)
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
        if row["source_expires_at"] and row["source_expires_at"] <= now():
            close_scan(db, row, "failed", EXPIRED_MESSAGE)
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
        project_provenance = db.execute(sa.select(provenance.c.scan_id).where(
            scope(provenance, org_id, project_id), provenance.c.scan_id == scan_id,
        )).scalar_one_or_none()
        if project_provenance and report["findings"]:
            from .artifact_review import redact_label
            db.execute(evidence_records.insert(), [
                {"org_id": org_id, "project_id": project_id, "scan_id": scan_id, **FindingObservation(
                    ordinal=index, rule=item["rule"], line=item["line"],
                    path=(redact_label(item.get("path")) or "")[:240] or None,
                    evidence_sha256=hashlib.sha256(item["evidence"].encode()).hexdigest(),
                ).model_dump()}
                for index, item in enumerate(report["findings"])
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


def reserve_model_connection(org_id, project_id, scan_id, lease):
    """Recheck the pinned provider and current manager opt-in before reserving budget."""
    from .identity import ROLE_ACTIONS, project_access
    from .model_connections import public_connection

    with platform_session() as db:
        bind_project(db, org_id, project_id)
        lock_project(db, org_id, project_id)
        row = select_scan(db, org_id, project_id, scan_id, lock=True)
        if (not row or row["state"] != "running" or row["lease"] != lease or row["lease_until"] <= now() or
                row["enrichment_reserved_at"] or (row["source_expires_at"] and row["source_expires_at"] <= now())):
            return None
        actor = project_access(db, project_id, row["user_id"])
        if not actor or actor.org_id != org_id or "scan" not in ROLE_ACTIONS[actor.role]:
            return None
        _, policy = project_policy(db, org_id, project_id)
        connection = public_connection(db, org_id, policy)
        if (not connection or row["input_meta"].get("model_connection") != connection["id"] or
                row["input_meta"].get("connection_model") != connection["model"] or
                row["input_meta"].get("connection_generation") != connection["generation"]):
            return None
        db.execute(scans.update().where(scans.c.id == scan_id).values(enrichment_reserved_at=now()))
        return connection


def expire_pending_artifacts():
    # The dispatcher has execute-only permissions for this operation on PostgreSQL.
    with platform_session() as db:
        if db.bind.dialect.name == "postgresql":
            return db.execute(sa.text("SELECT public.marsad_expire_artifacts()")).scalar_one()
        rows = db.execute(sa.select(scans).where(scans.c.raw.is_not(None), scans.c.source_expires_at <= now(),
                          scans.c.state.in_(["queued", "running"])).limit(100)).mappings().all()
        for row in rows:
            close_scan(db, row, "failed", EXPIRED_MESSAGE)
        return len(rows)


def scan_provenance(ctx, scan_id):
    ids = {"org_id": ctx.org_id, "project_id": ctx.project_id}
    with platform_session() as db:
        bind_project(db, **ids)
        sidecar = db.execute(sa.select(provenance).where(
            scope(provenance, **ids), provenance.c.scan_id == scan_id,
        )).mappings().first()
        if not sidecar:
            return None
        row = db.execute(sa.select(scans.c.id, scans.c.input_meta, scans.c.created_at, scans.c.source_expires_at).where(
            scope(scans, **ids), scans.c.id == scan_id,
        )).mappings().one()
        asset = None
        if sidecar["asset_id"]:
            ref = db.execute(sa.select(assets.c.reference).where(
                scope(assets, **ids), assets.c.id == sidecar["asset_id"],
            )).scalar_one()
            asset = Asset(id=sidecar["asset_id"], reference=ref,
                          source=sidecar["scope"].get("asset_source", "project_policy"))
        count = db.execute(sa.select(sa.func.count()).select_from(evidence_records).where(
            scope(evidence_records, **ids), evidence_records.c.scan_id == scan_id,
        )).scalar_one()
        return ScanProvenance(
            snapshot=SourceSnapshot(id=scan_id, sha256=sidecar["source_sha256"], kind=row["input_meta"]["kind"],
                                    bytes=row["input_meta"]["bytes"], created_at=timestamp(row["created_at"]),
                                    raw_expires_at=timestamp(row["source_expires_at"]),
                                    github=row["input_meta"].get("github")),
            scope=sidecar["scope"], asset=asset, tools=sidecar["tools"], evidence_count=count,
        )


def scan_evidence(ctx, scan_id, offset, limit):
    ids = {"org_id": ctx.org_id, "project_id": ctx.project_id}
    with platform_session() as db:
        bind_project(db, **ids)
        if db.execute(sa.select(provenance.c.scan_id).where(
            scope(provenance, **ids), provenance.c.scan_id == scan_id,
        )).scalar_one_or_none() is None:
            return None
        rows = db.execute(sa.select(evidence_records).where(
            scope(evidence_records, **ids), evidence_records.c.scan_id == scan_id,
        ).order_by(evidence_records.c.ordinal).offset(offset).limit(limit)).mappings()
        return [FindingObservation.model_validate(row) for row in rows]


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
