"""Authenticated project scanning, report access and scoped memory."""
import json
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
import sqlalchemy as sa

from . import platform_runtime as store
from . import advanced_reporting as advanced
from .analysis_mode import AnalysisMode, ModeUnavailable
from .artifact_review import EXTENDED_IDS, MAX_ARTIFACT, InputError, RULESET_VERSION, decode_payload, redact_label, safe_path
from .contracts import History, HistoryItem, Report
from .identity import ROLE_ACTIONS, require_project
from .intake_storage import StorageUnavailable
from .personal_intake import compatible_zip
from .scan_contracts import (
    ArtifactKind, DEFAULT_INPUTS, FindingObservation, ModelConnection, ScanProfile, ScanProvenance,
    TechnicalRegistry, analyzer_plan, manifests,
)
from .rules import RULES

router = APIRouter(prefix="/api/platform/projects/{project_id}", tags=["Project review"])


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={
        "examples": [{"kind": "html", "name": "evidence.html", "content": "PHA+ZXZpZGVuY2U8L3A+",
                      "scope_version": 0, "acknowledge_scope": True}],
    })
    kind: ArtifactKind
    name: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=4, max_length=2_666_668)
    enrich: bool = Field(False, json_schema_extra={"deprecated": True})
    scope_version: int | None = Field(default=None, ge=0)
    acknowledge_scope: bool = False
    model_connection: ModelConnection | None = None
    target_reference: str | None = Field(default=None, max_length=250)
    analysis_mode: AnalysisMode | None = None

    @model_validator(mode="after")
    def extension(self):
        expected = {"html": (".html", ".htm"), "repository": (".zip",),
                    "har": (".har",), "config": (".json",), "openapi": (".json",), "zap": (".json",)}
        if "/" in self.name or not self.name.lower().endswith(expected[self.kind]):
            raise ValueError("Invalid artifact extension")
        safe_path(self.name)
        if self.scope_version is not None and not self.acknowledge_scope:
            raise ValueError("The reviewed scope must be acknowledged")
        if self.model_connection is not None and self.scope_version is None:
            raise ValueError("A model connection requires a reviewed scope version")
        if self.target_reference is not None:
            if self.kind not in {"har", "openapi", "zap"} or self.scope_version is None:
                raise ValueError("A reference requires a reviewed web or API artifact")
            self.target_reference = store.web_origin(self.target_reference)
            if not self.target_reference:
                raise ValueError("Invalid website reference")
        return self


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_kinds: list[ArtifactKind] = Field(min_length=1, max_length=len(DEFAULT_INPUTS))
    base_url: str | None = Field(default=None, max_length=250)
    rules: dict = Field(default_factory=dict, max_length=30)
    expected_version: int | None = Field(default=None, ge=0)
    model_connection: ModelConnection | None = None

    @model_validator(mode="after")
    def validate_settings(self):
        if self.base_url:
            url = urlsplit(self.base_url)
            _ = url.port
            if (url.scheme not in {"https", "http"} or not url.hostname or url.username is not None or
                    url.password is not None or url.query or url.fragment):
                raise ValueError("Target URL must be a URL without credentials, query, or fragment")
        if len(json.dumps(self.rules, ensure_ascii=True, allow_nan=False)) > 12_000:
            raise ValueError("Policy exceeds the allowed size")
        if {"allowed_kinds", "base_url", "version", "model_connection", "model_grant_id", "_analysis_plan", "_ruleset_version"} & self.rules.keys():
            raise ValueError("Reserved policy key")
        return self


class Knowledge(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    reference: str = Field(min_length=1, max_length=500)
    note: str = Field(min_length=1, max_length=2000)


def missing():
    raise HTTPException(404, "العنصر غير متاح في المشروع ده.")


def project(request, project_id, action):
    return require_project(request, project_id, action)


@router.post("/scans", status_code=202)
def submit(project_id: str, body: Submission, request: Request,
           key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)]):
    ctx = project(request, project_id, "scan")
    if ctx.owner_user_id and (body.kind != "repository" or body.enrich):
        raise HTTPException(422, "المدخل المتاح حاليًا للمشاريع الشخصية هو ZIP.")
    try:
        raw = decode_payload(body.content)
        envelope = {"kind": body.kind, "name": redact_label(body.name), "bytes": len(raw), "enrich": body.enrich}
        if ctx.owner_user_id:
            return compatible_zip(ctx, envelope, raw, key, scope_version=body.scope_version,
                                  model_connection=body.model_connection, analysis_mode=body.analysis_mode)
        return store.create_scan(ctx, envelope, raw, key,
                                 scope_version=body.scope_version, model_connection=body.model_connection,
                                 target_reference=body.target_reference, analysis_mode=body.analysis_mode)
    except ModeUnavailable as exc:
        raise HTTPException(422, str(exc)) from None
    except InputError as exc:
        raise HTTPException(422, str(exc)) from None
    except StorageUnavailable:
        raise HTTPException(503, "تخزين اللقطات غير متاح مؤقتًا.") from None
    except store.Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except store.QueueLimit:
        raise HTTPException(429, "وصل المشروع لحد الفحوصات المؤقت. حاول بعد دقيقة.",
                            headers={"Retry-After": "60"}) from None


@router.get("/scans")
def list_scans(project_id: str, request: Request):
    ctx = project(request, project_id, "read")
    with store.platform_session() as db:
        store.bind_project_context(db, ctx)
        names = ["id", "state", "input_meta", "attempt", "cursor", "created_at", "updated_at"]
        rows = db.execute(sa.select(*(store.scans.c[name] for name in names)).where(
            store.scope(store.scans, ctx.org_id, ctx.project_id),
        ).order_by(store.scans.c.created_at.desc(), store.scans.c.id.desc()).limit(100)).mappings()
        return {"scans": [store.scan_view(row) for row in rows]}


@router.get("/scans/{scan_id}")
def status(project_id: str, scan_id: str, request: Request, after: Annotated[int, Query(ge=0)] = 0):
    ctx = project(request, project_id, "read")
    view = store.scan_status(ctx, scan_id, after)
    return view if view else missing()


@router.get("/scans/{scan_id}/provenance", response_model=ScanProvenance)
def scan_provenance(project_id: str, scan_id: str, request: Request):
    result = store.scan_provenance(project(request, project_id, "read"), scan_id)
    return result if result is not None else missing()


@router.get("/scans/{scan_id}/evidence", response_model=list[FindingObservation])
def scan_evidence(project_id: str, scan_id: str, request: Request,
                  offset: Annotated[int, Query(ge=0, le=5000)] = 0,
                  limit: Annotated[int, Query(ge=1, le=100)] = 50):
    result = store.scan_evidence(project(request, project_id, "read"), scan_id, offset, limit)
    return result if result is not None else missing()


@router.post("/scans/{scan_id}/cancel")
def cancel_scan(project_id: str, scan_id: str, request: Request):
    ctx = project(request, project_id, "scan")
    view = store.cancel(ctx, scan_id)
    return view if view else missing()


@router.get("/policy")
def read_policy(project_id: str, request: Request):
    ctx = project(request, project_id, "read")
    from .model_connections import public_connection

    with store.platform_session() as db:
        store.bind_project_context(db, ctx)
        version, policy = store.project_policy(db, ctx.org_id, ctx.project_id)
        connection = public_connection(db, ctx.org_id, policy)
    if ctx.owner_user_id:
        # PUT accepts only ["repository"] for a personal project, so GET must not offer more.
        policy = {**policy, "allowed_kinds": ["repository"]}
    return policy_view(version, policy, connection)


def project_memory_policy(ctx, row):
    view = dict(row) if row else {"version": 0, "policy": {"allowed_kinds": list(DEFAULT_INPUTS)}}
    if ctx.owner_user_id:
        view["policy"] = {**view["policy"], "allowed_kinds": ["repository"]}
    return view


def policy_view(version, policy, connection):
    details = {key: value for key, value in policy.items() if key not in {"model_grant_id", "model_connection"}}
    if connection:
        details["model_connection"] = connection["id"]
    return {"version": version, "policy": details}


@router.get("/scan-profile", response_model=ScanProfile)
def scan_profile(project_id: str, request: Request):
    from .model_connections import connection_is_ready, scan_connection

    ctx = project(request, project_id, "read")
    with store.platform_session() as db:
        store.bind_project_context(db, ctx)
        version, policy = store.project_policy(db, ctx.org_id, ctx.project_id)
        connection = scan_connection(db, ctx, policy)
    can_enrich = "scan" in ROLE_ACTIONS[ctx.role] and connection_is_ready(connection)
    configured_tools = {kind: analyzer_plan(kind) for kind in policy.get("allowed_kinds", DEFAULT_INPUTS)}
    if ctx.owner_user_id:
        configured_tools = {kind: tools for kind, tools in configured_tools.items() if kind == "repository"}
    return ScanProfile(scope_version=version, allowed_kinds=[kind for kind, plans in configured_tools.items() if plans],
                       max_bytes=MAX_ARTIFACT, asset_linked=bool(policy.get("base_url")),
                       enrichment_available=can_enrich, model_connection=connection if can_enrich else None,
                       tools_by_input=configured_tools)


@router.get("/technical", response_model=TechnicalRegistry)
def technical(project_id: str, request: Request):
    from .model_connections import connection_is_ready, public_connection

    ctx = project(request, project_id, "manage")
    with store.platform_session() as db:
        store.bind_project_context(db, ctx)
        version, policy = store.project_policy(db, ctx.org_id, ctx.project_id)
        connection = public_connection(db, ctx.org_id, policy)
        server = public_connection(db, ctx.org_id)
    tools, roles = manifests()
    return TechnicalRegistry(scope_version=version, model_connection=connection["id"] if connection else None,
                             server_connection=server, server_ready=connection_is_ready(server), tools=tools, roles=roles,
                             permissions={role: sorted(actions) for role, actions in ROLE_ACTIONS.items()})


@router.put("/policy")
def update_policy(project_id: str, request: Request, body: Policy):
    from .model_connections import public_connection

    ctx = project(request, project_id, "manage")
    if ctx.owner_user_id and (body.allowed_kinds != ["repository"] or body.model_connection):
        raise HTTPException(422, "سياسة المشروع الشخصي تقبل ZIP بالفحص المحلي حاليًا.")
    policy = {"allowed_kinds": list(dict.fromkeys(body.allowed_kinds)), "base_url": body.base_url, **body.rules}
    with store.platform_session() as db:
        store.bind_project_context(db, ctx)
        if not store.lock_project(db, ctx.org_id, ctx.project_id):
            missing()
        condition = store.scope(store.settings, ctx.org_id, ctx.project_id)
        version, existing = store.project_policy(db, ctx.org_id, ctx.project_id)
        if body.expected_version is not None and body.expected_version != version:
            raise HTTPException(409, "سياسة المشروع اتغيّرت. ارجع حمّل الإعدادات.")
        connection = None
        if "model_connection" not in body.model_fields_set:
            connection = public_connection(db, ctx.org_id, existing)
        elif body.model_connection is not None:
            connection = public_connection(db, ctx.org_id)
            if connection is None:
                raise HTTPException(409, "اتصال الموديل المطلوب غير متاح.")
        if connection:
            policy.update(model_connection=connection["id"], model_grant_id=connection["grant_id"])
        if version == 0:
            db.execute(store.settings.insert().values(org_id=ctx.org_id, project_id=ctx.project_id,
                                                      version=1, policy=policy))
            return policy_view(1, policy, connection)
        db.execute(store.settings.update().where(condition).values(version=version + 1, policy=policy))
        return policy_view(version + 1, policy, connection)


def load(ctx, report_id):
    return advanced.read_report(ctx, report_id)[0]


@router.get("/reports", response_model=History)
def reports(project_id: str, request: Request):
    ctx = project(request, project_id, "read")
    with store.platform_session() as db:
        store.bind_project_context(db, ctx)
        rows = db.execute(sa.select(store.scans.c.report_index).where(
            store.scope(store.scans, ctx.org_id, ctx.project_id), store.scans.c.state.in_(["completed", "partial"]),
        ).order_by(store.scans.c.updated_at.desc()).limit(100)).scalars()
        return History(reports=[HistoryItem.model_validate(value) for value in rows])


@router.get("/dashboard")
def project_dashboard(project_id: str, request: Request):
    from . import dashboard

    return JSONResponse(dashboard.read(project(request, project_id, "read")), headers={"Cache-Control": "no-store"})


@router.get("/reports/{report_id}", response_model=Report)
def report_detail(project_id: str, report_id: str, request: Request):
    return load(project(request, project_id, "read"), report_id)


@router.get("/reports/{report_id}/download")
def export(project_id: str, report_id: str, request: Request, lang: Literal["ar", "en"] = "en",
           format: Literal["html", "json", "pdf"] = "html"):
    from .main import report_html
    value = load(project(request, project_id, "export"), report_id)
    if format == "pdf":
        from .report_pdf import pdf_download
        return pdf_download(value, lang)
    report = value.model_dump(mode="json")
    filename = "basira-report.json" if format == "json" else f"basira-report-{lang}.html"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if format == "json":
        return JSONResponse(report, headers=headers)
    headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    return HTMLResponse(report_html(report, lang), headers=headers)


@router.get("/reports/{report_id}/compare")
def compare_reports(project_id: str, report_id: str, request: Request,
                    baseline: Annotated[str, Query(pattern=r"^[a-f0-9]{32}$")]):
    ctx = project(request, project_id, "read")
    current, policy = advanced.read_report(ctx, report_id)
    previous, baseline_policy = advanced.read_report(ctx, baseline)
    return advanced.compare(current, previous, policy, baseline_policy)


@router.get("/reports/{report_id}/review")
def read_review(project_id: str, report_id: str, request: Request):
    return advanced.get_review(project(request, project_id, "read"), report_id)


@router.post("/reports/{report_id}/review")
def update_review(project_id: str, report_id: str, request: Request, body: advanced.ReviewAction):
    return advanced.change_review(project(request, project_id, "finding"), report_id, body)


@router.get("/memory")
def memory(project_id: str, request: Request):
    ctx = project(request, project_id, "read")
    with store.platform_session() as db:
        store.bind_project_context(db, ctx)
        def scoped(table):
            return store.scope(table, ctx.org_id, ctx.project_id)
        scans = store.scans
        last = db.execute(sa.select(scans.c.id, scans.c.state, scans.c.created_at).where(scoped(scans))
                          .order_by(scans.c.created_at.desc()).limit(20)).mappings().all()
        knowledge = db.execute(sa.select(store.notes.c.id, store.notes.c.title, store.notes.c.reference,
                                         store.notes.c.note, store.notes.c.created_at).where(
            scoped(store.notes), store.notes.c.revoked_at.is_(None),
        ).order_by(store.notes.c.created_at.desc()).limit(50)).mappings()
        observations = db.execute(sa.select(
            store.findings.c.fingerprint, store.findings.c.rule, sa.func.sum(store.findings.c.count).label("count"),
            sa.func.coalesce(advanced.reviews.c.status, "open").label("status"),
        ).select_from(store.findings).outerjoin(advanced.reviews, sa.and_(scoped(advanced.reviews),
            advanced.reviews.c.fingerprint == store.findings.c.fingerprint))
            .where(scoped(store.findings)).group_by(store.findings.c.fingerprint, store.findings.c.rule,
                                                   advanced.reviews.c.status)
            .order_by(sa.func.sum(store.findings.c.count).desc(), store.findings.c.fingerprint).limit(50)).mappings()
        policy = db.execute(sa.select(store.settings.c.version, store.settings.c.policy).where(
            scoped(store.settings),
        )).mappings().first()
        return {
            "working": [item["id"] for item in last if item["state"] not in store.TERMINAL],
            "episodic": [{**item, "created_at": store.timestamp(item["created_at"])} for item in last],
            "semantic": [{**item, "created_at": store.timestamp(item["created_at"])} for item in knowledge],
            "procedural": {"version": RULESET_VERSION, "rules": list(RULES) + EXTENDED_IDS},
            "project": project_memory_policy(ctx, policy),
            "finding": [dict(item) for item in observations],
        }


@router.post("/memory/knowledge", status_code=201)
def add_note(project_id: str, request: Request, body: Knowledge):
    ctx = project(request, project_id, "manage")
    identifier = uuid4().hex
    with store.platform_session() as db:
        store.bind_project_context(db, ctx)
        db.execute(store.notes.insert().values(id=identifier, org_id=ctx.org_id, project_id=ctx.project_id,
                   reviewer_id=ctx.user_id, created_at=store.now(), **body.model_dump()))
    return {"id": identifier}


@router.delete("/memory/knowledge/{note_id}")
def delete_note(project_id: str, note_id: str, request: Request):
    ctx = project(request, project_id, "manage")
    with store.platform_session() as db:
        store.bind_project_context(db, ctx)
        row = db.execute(store.notes.update().where(
            store.scope(store.notes, ctx.org_id, ctx.project_id), store.notes.c.id == note_id,
            store.notes.c.revoked_at.is_(None),
        ).values(revoked_at=store.now(), note="", reference=""))
        if not row.rowcount:
            missing()
    return {"revoked": True}
