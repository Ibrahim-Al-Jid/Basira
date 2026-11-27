"""Explicit relationships between reports with a shared project asset."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa

from . import platform_runtime as store
from .identity import ROLE_ACTIONS, require_project
from .phase9_contracts import Identifier
from .platform_db import new_id, tenant_session

router = APIRouter(prefix="/api/platform/projects/{project_id}/reports/{report_id}",
                   tags=["Linked project evidence"])
CODE = {"repository"}
WEB = {"html", "har", "zap", "openapi"}
MAX_LINKS = 50

links = sa.Table(
    "project_evidence_links", store.metadata,
    sa.Column("id", sa.String(32), primary_key=True, default=new_id),
    sa.Column("org_id", sa.String(32), nullable=False),
    sa.Column("project_id", sa.String(32), nullable=False),
    sa.Column("code_scan", sa.String(32), nullable=False),
    sa.Column("web_scan", sa.String(32), nullable=False),
    sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False, default=store.now),
    *[sa.ForeignKeyConstraint(("org_id", "project_id", column),
                              ("project_scan_provenance.org_id", "project_scan_provenance.project_id",
                               "project_scan_provenance.scan_id"), ondelete="CASCADE")
      for column in ("code_scan", "web_scan")],
    sa.UniqueConstraint("org_id", "project_id", "code_scan", "web_scan", name="uq_evidence_links_pair"),
    sa.CheckConstraint("code_scan <> web_scan", name="ck_evidence_link_distinct"),
    sa.Index("ix_evidence_links_web", "org_id", "project_id", "web_scan"),
)


class LinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_id: Identifier


def published(ctx):
    scan, provenance = store.scans, store.provenance
    return sa.select(scan.c.id, scan.c.input_meta, scan.c.report_index, scan.c.created_at,
                     provenance.c.asset_id).join(provenance, sa.and_(
        provenance.c.org_id == scan.c.org_id,
        provenance.c.project_id == scan.c.project_id,
        provenance.c.scan_id == scan.c.id,
    ), isouter=True).where(
        store.scope(scan, ctx.org_id, ctx.project_id), scan.c.state.in_(("completed", "partial")),
    )


def report(db, ctx, report_id):
    row = db.execute(published(ctx).where(store.scans.c.id == report_id)).mappings().first()
    if row is None:
        if db.scalar(sa.select(store.legacy.c.legacy_id).where(
            store.scope(store.legacy, ctx.org_id, ctx.project_id), store.legacy.c.legacy_id == report_id,
        )):
            return None
        raise HTTPException(404, "التقرير غير متاح.")
    return row


def match_links(ctx, identifier):
    return sa.and_(store.scope(links, ctx.org_id, ctx.project_id),
                   sa.or_(links.c.code_scan == identifier, links.c.web_scan == identifier))


def paired(row, identifier):
    return row.web_scan if row.code_scan == identifier else row.code_scan


def available(db, ctx, identifier):
    rows = db.execute(sa.select(links.c.id, links.c.code_scan, links.c.web_scan)
                      .where(match_links(ctx, identifier)).order_by(links.c.created_at.desc())
                      .limit(MAX_LINKS)).mappings().all()
    if not rows:
        return []
    peers = {paired(row, identifier): row.id for row in rows}
    reports = {row.id: row for row in db.execute(published(ctx).where(store.scans.c.id.in_(peers))).mappings()}
    return [{
        "id": peers[report_id], "report_id": report_id, "kind": reports[report_id].input_meta["kind"],
        "name": reports[report_id].input_meta["name"], "created_at": store.timestamp(reports[report_id].created_at),
        "finding_count": (reports[report_id].report_index or {}).get("finding_count", 0),
    } for report_id in peers if report_id in reports]


def choices(row):
    if row is None or not row.asset_id:
        return ()
    kind = row.input_meta.get("kind")
    return WEB if kind in CODE else CODE if kind in WEB else ()


@router.get("/links")
def read_links(project_id: Identifier, report_id: Identifier, request: Request):
    ctx = require_project(request, project_id, "read")
    with tenant_session(ctx) as db:
        row = report(db, ctx, report_id)
        return {"links": available(db, ctx, report_id),
                "can_link": bool(choices(row)) and "manage" in ROLE_ACTIONS[ctx.role]}


@router.get("/link-candidates")
def candidates(project_id: Identifier, report_id: Identifier, request: Request):
    ctx = require_project(request, project_id, "manage")
    with tenant_session(ctx) as db:
        row = report(db, ctx, report_id)
        kinds = choices(row)
        if not kinds:
            return {"reports": []}
        linked = sa.select(sa.case(
            (links.c.code_scan == report_id, links.c.web_scan), else_=links.c.code_scan
        )).where(match_links(ctx, report_id))
        reports = db.execute(published(ctx).where(
            store.provenance.c.asset_id == row.asset_id,
            store.scans.c.input_meta["kind"].as_string().in_(kinds),
            store.scans.c.id.not_in(linked),
        ).order_by(store.scans.c.created_at.desc()).limit(MAX_LINKS)).mappings()
        return {"reports": [{"id": item.id, "kind": item.input_meta["kind"], "name": item.input_meta["name"],
                             "created_at": store.timestamp(item.created_at)}
                            for item in reports]}


@router.post("/links")
def create_link(project_id: Identifier, report_id: Identifier, body: LinkInput, request: Request):
    ctx = require_project(request, project_id, "manage")
    with tenant_session(ctx) as db:
        store.lock_project(db, ctx.org_id, ctx.project_id)
        first, second = report(db, ctx, report_id), report(db, ctx, body.report_id)
        if (not choices(first) or second is None or first.asset_id != second.asset_id
                or second.input_meta["kind"] not in choices(first)):
            raise HTTPException(409, "اختار تقرير كود وتقرير ويب أو API لنفس الأصل المسجّل في المشروع.")
        code, web = (first.id, second.id) if first.input_meta["kind"] in CODE else (second.id, first.id)
        pair = sa.and_(store.scope(links, ctx.org_id, ctx.project_id),
                       links.c.code_scan == code, links.c.web_scan == web)
        if db.scalar(sa.select(links.c.id).where(pair)) is None:
            for identifier in (code, web):
                if db.scalar(sa.select(sa.func.count()).select_from(links)
                             .where(match_links(ctx, identifier))) >= MAX_LINKS:
                    raise HTTPException(409, "وصل التقرير للحد الأقصى من الأدلة المرتبطة.")
            db.execute(links.insert().values(org_id=ctx.org_id, project_id=ctx.project_id,
                                             code_scan=code, web_scan=web, created_by=ctx.user_id))
        return {"links": available(db, ctx, report_id), "can_link": True}


@router.delete("/links/{link_id}", status_code=204)
def remove_link(project_id: Identifier, report_id: Identifier, link_id: Identifier, request: Request):
    ctx = require_project(request, project_id, "manage")
    with tenant_session(ctx) as db:
        store.lock_project(db, ctx.org_id, ctx.project_id)
        if not db.execute(links.delete().where(match_links(ctx, report_id), links.c.id == link_id)).rowcount:
            raise HTTPException(404, "الرابط غير متاح.")
