"""Authenticated project scanning, report access and scoped memory."""
from datetime import timedelta
import json
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, model_validator
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from . import platform_runtime as store
from . import advanced_reporting as advanced
from .artifact_review import EXTENDED_IDS, InputError, RULESET_VERSION, decode_payload, redact_label, safe_path
from .contracts import History, HistoryItem, Report, history_item
from .identity import require_project
from .rules import RULES

router = APIRouter(prefix="/api/platform/projects/{project_id}", tags=["Project review"])
ArtifactKind = Literal["html", "repository", "har", "config"]


class Submission(BaseModel):
    kind: ArtifactKind
    name: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=4, max_length=2_666_668)
    enrich: bool = False

    @model_validator(mode="after")
    def extension(self):
        expected = {"html": (".html", ".htm"), "repository": (".zip",),
                    "har": (".har",), "config": (".json",)}
        if "/" in self.name or not self.name.lower().endswith(expected[self.kind]):
            raise ValueError("Invalid artifact extension")
        safe_path(self.name)
        return self


class Policy(BaseModel):
    allowed_kinds: list[ArtifactKind] = Field(min_length=1, max_length=4)
    base_url: str | None = Field(default=None, max_length=250)
    rules: dict = Field(default_factory=dict, max_length=30)

    @model_validator(mode="after")
    def validate_settings(self):
        if self.base_url:
            url = urlsplit(self.base_url)
            if (url.scheme not in {"https", "http"} or not url.hostname or url.username is not None or
                    url.password is not None or url.query or url.fragment):
                raise ValueError("Target URL must be a URL without credentials, query, or fragment")
        if len(json.dumps(self.rules, ensure_ascii=True)) > 12_000:
            raise ValueError("Policy exceeds the allowed size")
        if {"allowed_kinds", "base_url", "version"} & self.rules.keys():
            raise ValueError("Reserved policy key")
        return self


class Knowledge(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    reference: str = Field(min_length=1, max_length=500)
    note: str = Field(min_length=1, max_length=2000)


class Claim(BaseModel):
    confirm: Literal[True]


def missing():
    raise HTTPException(404, "العنصر غير متاح في المشروع ده.")


def project(request, project_id, action):
    return require_project(request, project_id, action)


@router.post("/scans", status_code=202)
def submit(project_id: str, body: Submission, request: Request,
           key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)]):
    ctx = project(request, project_id, "scan")
    try:
        raw = decode_payload(body.content)
        return store.create_scan(ctx, {"kind": body.kind, "name": redact_label(body.name), "bytes": len(raw),
                                       "enrich": body.enrich}, raw, key)
    except InputError as exc:
        raise HTTPException(422, str(exc)) from None
    except store.Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except store.QueueLimit:
        raise HTTPException(429, "وصل المشروع لحد الفحوصات المؤقت. حاول بعد دقيقة.",
                            headers={"Retry-After": "60"}) from None


@router.get("/scans")
def list_scans(project_id: str, request: Request):
    ctx = project(request, project_id, "read")
    with store.platform_session() as db:
        store.bind_project(db, ctx.org_id, ctx.project_id)
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


@router.post("/scans/{scan_id}/cancel")
def cancel_scan(project_id: str, scan_id: str, request: Request):
    ctx = project(request, project_id, "scan")
    view = store.cancel(ctx, scan_id)
    return view if view else missing()


@router.get("/policy")
def read_policy(project_id: str, request: Request):
    ctx = project(request, project_id, "read")
    with store.platform_session() as db:
        store.bind_project(db, ctx.org_id, ctx.project_id)
        row = db.execute(sa.select(store.settings).where(
            store.scope(store.settings, ctx.org_id, ctx.project_id),
        )).mappings().first()
        return {"version": row["version"], "policy": row["policy"]} if row else {
            "version": 0, "policy": {"allowed_kinds": ["html"]},
        }


@router.put("/policy")
def update_policy(project_id: str, request: Request, body: Policy):
    ctx = project(request, project_id, "manage")
    policy = {"allowed_kinds": list(dict.fromkeys(body.allowed_kinds)), "base_url": body.base_url, **body.rules}
    with store.platform_session() as db:
        store.bind_project(db, ctx.org_id, ctx.project_id)
        projects = store.metadata.tables["projects"]
        db.execute(sa.select(projects.c.id).where(projects.c.org_id == ctx.org_id,
                                                  projects.c.id == ctx.project_id).with_for_update()).one()
        condition = store.scope(store.settings, ctx.org_id, ctx.project_id)
        version = db.execute(sa.select(store.settings.c.version).where(condition)).scalar_one_or_none()
        if version is None:
            db.execute(store.settings.insert().values(org_id=ctx.org_id, project_id=ctx.project_id,
                                                      version=1, policy=policy))
            return {"version": 1, "policy": policy}
        db.execute(store.settings.update().where(condition).values(version=version + 1, policy=policy))
        return {"version": version + 1, "policy": policy}


def load(ctx, report_id):
    return advanced.read_report(ctx, report_id)[0]


@router.get("/reports", response_model=History)
def reports(project_id: str, request: Request):
    ctx = project(request, project_id, "read")
    with store.platform_session() as db:
        store.bind_project(db, ctx.org_id, ctx.project_id)
        selection = sa.select(store.scans.c.report_index, store.scans.c.updated_at.label("sort_at")).where(
            store.scope(store.scans, ctx.org_id, ctx.project_id), store.scans.c.state.in_(["completed", "partial"]),
        ).union_all(sa.select(store.legacy.c.report_index, store.legacy.c.claimed_at.label("sort_at")).where(
            store.scope(store.legacy, ctx.org_id, ctx.project_id),
        )).subquery()
        rows = db.execute(sa.select(selection.c.report_index).order_by(selection.c.sort_at.desc()).limit(100)).scalars()
        return History(reports=[HistoryItem.model_validate(value) for value in rows])


@router.get("/reports/{report_id}", response_model=Report)
def report_detail(project_id: str, report_id: str, request: Request):
    return load(project(request, project_id, "read"), report_id)


@router.get("/reports/{report_id}/download")
def export(project_id: str, report_id: str, request: Request, lang: Literal["ar", "en"] = "en",
           format: Literal["html", "json", "sarif"] = "html"):
    from .main import report_html
    value = load(project(request, project_id, "export"), report_id)
    if format == "sarif":
        return JSONResponse(advanced.sarif(value, lang), headers={
            "Content-Disposition": 'attachment; filename="marsad-report.sarif"',
        })
    report = value.model_dump(mode="json")
    filename = "marsad-report.json" if format == "json" else f"marsad-report-{lang}.html"
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


@router.post("/reports/{report_id}/claim", status_code=201)
def claim_report(project_id: str, report_id: str, request: Request, body: Claim):
    from .main import claimable_legacy_report
    ctx = project(request, project_id, "scan")
    report = claimable_legacy_report(request, report_id)
    try:
        with store.platform_session() as db:
            store.bind_project(db, ctx.org_id, ctx.project_id)
            existing = db.execute(sa.select(store.legacy.c.legacy_id).where(
                store.scope(store.legacy, ctx.org_id, ctx.project_id), store.legacy.c.legacy_id == report_id,
            )).first()
            if not existing:
                db.execute(store.legacy.insert().values(legacy_id=report_id, org_id=ctx.org_id,
                           project_id=ctx.project_id, user_id=ctx.user_id,
                           report=report.model_dump(mode="json"), claimed_at=store.now(),
                           report_index=history_item(report).model_dump(mode="json")))
    except IntegrityError:
        raise HTTPException(409, "تعذّر ربط التقرير بالمشروع.") from None
    return {"id": report_id}


@router.get("/memory")
def memory(project_id: str, request: Request):
    ctx = project(request, project_id, "read")
    with store.platform_session() as db:
        store.bind_project(db, ctx.org_id, ctx.project_id)
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
            "project": dict(policy) if policy else {"version": 0, "policy": {"allowed_kinds": ["html"]}},
            "finding": [dict(item) for item in observations],
        }


@router.post("/memory/knowledge", status_code=201)
def add_note(project_id: str, request: Request, body: Knowledge):
    ctx = project(request, project_id, "manage")
    identifier = uuid4().hex
    with store.platform_session() as db:
        store.bind_project(db, ctx.org_id, ctx.project_id)
        db.execute(store.notes.insert().values(id=identifier, org_id=ctx.org_id, project_id=ctx.project_id,
                   reviewer_id=ctx.user_id, created_at=store.now(), **body.model_dump()))
    return {"id": identifier}


@router.delete("/memory/knowledge/{note_id}")
def delete_note(project_id: str, note_id: str, request: Request):
    ctx = project(request, project_id, "manage")
    with store.platform_session() as db:
        store.bind_project(db, ctx.org_id, ctx.project_id)
        row = db.execute(store.notes.update().where(
            store.scope(store.notes, ctx.org_id, ctx.project_id), store.notes.c.id == note_id,
            store.notes.c.revoked_at.is_(None),
        ).values(revoked_at=store.now(), note="", reference=""))
        if not row.rowcount:
            missing()
    return {"revoked": True}
