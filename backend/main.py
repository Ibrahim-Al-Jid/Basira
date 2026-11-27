"""Basira's same-origin HTTP API and React frontend."""
import asyncio
import base64
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .contracts import (
    CompleteEvent, ErrorEvent, History, HistoryItem, Report, Run,
    RunEvent, SourceInfo, StepEvent, history_item,
)
from .graph import GraphError, run_graph
from .artifact_review import RULESET_VERSION, catalog as rule_catalog, redact_label
from .offline_worker import scan_payload
from .taxonomy import public as taxonomy_public
from .platform_db import personal_projects_enabled

ROOT = Path(__file__).resolve().parents[1]
COOKIE = "basira_session"
SESSION_SECONDS = 30 * 86400
LEGACY_GRACE_SECONDS = 7 * 86400
app = FastAPI(title="Basira Agent Lab", version="2.3")


class RunStream(StreamingResponse):
    media_type = "application/x-ndjson"


fastapi_openapi = app.openapi


def describe_ndjson():
    schema = fastapi_openapi()
    media = schema["paths"]["/api/run"]["post"]["responses"]["200"]["content"]["application/x-ndjson"]
    if "x-itemSchema" not in media:
        item = media["schema"]
        item.pop("type", None)
        media["x-itemSchema"] = item
        media["schema"] = {"type": "string"}
    return schema


app.openapi = describe_ndjson


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    # Pydantic's default body may echo a submitted credential or HTML source.
    if request.url.path in {"/api/platform/auth/password/register", "/api/platform/auth/password/login"}:
        messages = {
            "email": "اكتب الإيميل بصيغة صحيحة.",
            "password": "راجع كلمة المرور. الحد الأقصى ١٢٨ حرف.",
        }
        if request.url.path.endswith("/register"):
            messages.update({
                "first_name": "اكتب الاسم الأول بحروف من غير أرقام أو شرطة سفلية.",
                "last_name": "اكتب اسم العائلة بحروف من غير أرقام أو شرطة سفلية.",
            })
        locations = {tuple(issue["loc"]) for issue in error.errors()}
        fields = [field for field in messages if ("body", field) in locations]
        detail = " ".join(messages[field] for field in fields) or "راجع الحقول المطلوبة لإنشاء الحساب أو تسجيل الدخول."
        return JSONResponse({"detail": detail, "fields": fields}, status_code=422)
    if request.url.path.startswith("/api/platform/"):
        detail = "راجع الحقول المطلوبة ونوع البيانات."
    else:
        detail = "راجع نوع وحجم مصدر HTML والحقول المدعومة."
    return JSONResponse({"detail": detail}, status_code=422)


@app.middleware("http")
async def protect_requests(request, call_next):
    path = request.url.path.rstrip("/")
    if personal_projects_enabled() and (
        path in {"/demo", "/api/run", "/api/history", "/api/reports"}
        or path.startswith(("/api/reports/", "/api/platform/organizations/", "/api/platform/invitations/"))
        or path == "/api/platform/organizations"
        or re.match(r"^/api/platform/projects/[^/]+/(?:grants|github-source)(?:/|$)", path)
        or re.fullmatch(r"/api/platform/projects/[^/]+/reports/[^/]+/claim", path)
    ):
        return JSONResponse({"detail": "المسار غير متاح."}, status_code=404,
                            headers={"Cache-Control": "no-store"})
    if request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "مصدر الطلب غير مسموح."}, status_code=403,
                                headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    return await call_next(request)


@contextmanager
def database():
    path = Path(os.environ.get("BASIRA_DB_PATH", ROOT / "data" / "basira.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=5)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions(owner TEXT PRIMARY KEY, expires_at INTEGER);
            CREATE TABLE IF NOT EXISTS legacy_session_window(id INTEGER PRIMARY KEY CHECK(id = 1), ends_at INTEGER);
            CREATE TABLE IF NOT EXISTS reports(
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, created_at TEXT NOT NULL,
                model TEXT NOT NULL, finding_count INTEGER NOT NULL, report_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS owner_reports ON reports(owner,created_at DESC);
            CREATE TABLE IF NOT EXISTS report_index(
                id TEXT PRIMARY KEY REFERENCES reports(id) ON DELETE CASCADE, summary_json TEXT NOT NULL
            );
        """)
        if "expires_at" not in {row["name"] for row in db.execute("PRAGMA table_info(sessions)")}:
            db.execute("BEGIN IMMEDIATE")
            if "expires_at" not in {row["name"] for row in db.execute("PRAGMA table_info(sessions)")}:
                db.execute("ALTER TABLE sessions ADD COLUMN expires_at INTEGER")
                db.execute("INSERT INTO legacy_session_window VALUES (1,?)", (int(time.time()) + LEGACY_GRACE_SECONDS,))
            db.commit()
        yield db


def owner_key(token):
    return hashlib.sha256(token.encode()).hexdigest()


def active_owner(db, token, *, allow_legacy=True):
    if len(token) != 43:
        return None
    owner = owner_key(token)
    row = db.execute("SELECT expires_at FROM sessions WHERE owner=?", (owner,)).fetchone()
    if not row:
        return None
    deadline = row["expires_at"]
    if deadline is None and allow_legacy:
        window = db.execute("SELECT ends_at FROM legacy_session_window WHERE id=1").fetchone()
        deadline = window["ends_at"] if window else None
    return owner if deadline is not None and deadline > int(time.time()) else None


def session(request):
    token = request.cookies.get(COOKIE, "")
    with database() as db:
        owner = active_owner(db, token)
        if owner:
            return owner, None
        token = secrets.token_urlsafe(32)
        owner = owner_key(token)
        db.execute("INSERT INTO sessions(owner, expires_at) VALUES(?,?)", (owner, int(time.time()) + SESSION_SECONDS))
    return owner, token


def set_session(response, token, request):
    if token:
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict",
                            secure=request.url.scheme == "https", max_age=SESSION_SECONDS)
    return response


@app.get("/api/catalog")
def security_catalog():
    return rule_catalog()


@app.get("/api/taxonomy")
def vulnerability_taxonomy():
    return taxonomy_public()


def summaries(owner):
    with database() as db:
        rows = db.execute("""
            SELECT i.summary_json, CASE WHEN i.id IS NULL THEN r.report_json END AS legacy_json
            FROM reports AS r LEFT JOIN report_index AS i ON i.id = r.id
            WHERE r.owner = ? ORDER BY r.created_at DESC, r.id DESC LIMIT 100
        """, (owner,)).fetchall()
        reports = []
        for row in rows:
            if row["summary_json"] is not None:
                reports.append(HistoryItem.model_validate_json(row["summary_json"]))
                continue
            item = history_item(Report.model_validate_json(row["legacy_json"]))
            reports.append(item)
            db.execute("INSERT OR IGNORE INTO report_index (id, summary_json) SELECT id, ? FROM reports WHERE id = ?",
                       (item.model_dump_json(), item.id))
    return History(reports=reports)


@app.get("/api/history", response_model=History)
def history(request: Request):
    owner, token = session(request)
    return set_session(JSONResponse(summaries(owner).model_dump(mode="json")), token, request)


def save_report(owner, report):
    item = history_item(Report.model_validate(report))
    with database() as db:
        db.execute("INSERT INTO reports VALUES(?,?,?,?,?,?)", (
            report["id"], owner, report["created_at"], report["model"] or "", len(report["findings"]),
            json.dumps(report, ensure_ascii=False),
        ))
        db.execute("INSERT INTO report_index (id, summary_json) VALUES (?, ?)", (item.id, item.model_dump_json()))
        db.execute("DELETE FROM reports WHERE owner=? AND id NOT IN "
                   "(SELECT id FROM reports WHERE owner=? ORDER BY created_at DESC, id DESC LIMIT 100)", (owner, owner))


@app.post("/api/run", response_class=RunStream, responses={
    200: {"model": RunEvent, "description": "One step, complete, or error JSON object per NDJSON line.",
          "content": {"application/x-ndjson": {}}},
})
async def run(body: Run, request: Request):
    owner, token = session(request)
    scan_id = uuid4().hex
    source_info = body.source_info
    name = source_info.name if source_info else None
    normalized = body.source.replace("\r\n", "\n").replace("\r", "\n")
    source = SourceInfo(kind=source_info.kind if source_info else "paste", name=name,
                        bytes=len(body.source.encode("utf-8")), lines=normalized.count("\n") + 1)

    async def events():
        queue = asyncio.Queue()
        steps = []

        async def emit(event):
            step = StepEvent.model_validate({
                **event, "role": event["node"].split(":")[0], "scan_id": scan_id,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            })
            steps.append(step.model_dump(exclude={"type"}))
            await queue.put(step)

        async def fail(message):
            await queue.put(ErrorEvent(scan_id=scan_id, message=message))

        async def execute():
            try:
                async with asyncio.timeout(300):
                    if body.profile == "extended":
                        filename = redact_label(source.name) or ("basira-sample.html" if source.kind == "sample" else "source.html")
                        payload = {"kind": "html", "name": filename, "policy": {},
                                   "content": base64.b64encode(body.source.encode("utf-8")).decode("ascii")}
                        answer = await asyncio.to_thread(scan_payload, payload)
                        if "error" in answer:
                            raise GraphError(answer["error"])
                        result = answer["result"]
                        for item in result.pop("steps"):
                            await emit(item)
                        result["ruleset_version"] = RULESET_VERSION
                        result["status"] = "partial" if any(row["status"] == "error" for row in result["coverage"]) else "completed"
                    else:
                        result = await run_graph(body.source, None, None, emit)
                report = Report.model_validate({
                    **result, "id": scan_id, "schema_version": 2,
                    "created_at": datetime.now(timezone.utc).isoformat(), "model": None,
                    "steps": steps, "source": source,
                    "enrichment": result.get("enrichment"),
                })
                save_report(owner, report.model_dump(mode="json"))
                await queue.put(CompleteEvent(report=report))
            except TimeoutError:
                await fail("انتهت مهلة التشغيل. حاول تاني أو شغّل الفحص المحلي.")
            except GraphError as exc:
                await fail(str(exc))
            except Exception:
                await fail("تعذّر استكمال التشغيل. راجع المدخل وحاول تاني.")

        task = asyncio.create_task(execute())
        try:
            while True:
                event = await queue.get()
                yield event.model_dump_json() + "\n"
                if event.type != "step":
                    break
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    response = RunStream(events(), headers={"X-Accel-Buffering": "no"})
    return set_session(response, token, request)


def load_report(request, report_id, *, allow_legacy=True):
    token = request.cookies.get(COOKIE, "")
    with database() as db:
        owner = active_owner(db, token, allow_legacy=allow_legacy)
        row = db.execute("SELECT report_json FROM reports WHERE id=? AND owner=?", (report_id, owner)).fetchone()
    if not row:
        raise HTTPException(404, "التقرير غير موجود في الجلسة دي.")
    return Report.model_validate_json(row[0])


def claimable_legacy_report(request, report_id):
    return load_report(request, report_id, allow_legacy=False)


@app.get("/api/reports/{report_id}", response_model=Report)
def report_detail(report_id: str, request: Request):
    return load_report(request, report_id)


def report_html(report, lang):
    ar = lang == "ar"
    def t(arabic, english):
        return arabic if ar else english
    def esc(value):
        return html.escape(str(value), quote=True)
    artifact = report.get("input_artifact")
    title = (t("تقرير فحص المشروع", "Project security review") if artifact
             else t("تقرير مراجعة أمان HTML", "HTML security review"))
    metrics = report["metrics"]
    source = report["source"]
    source_labels = {"file": t("ملف HTML", "HTML file"), "sample": t("العينة المرجعية", "Reference sample"),
                     "paste": t("كود ملصوق", "Pasted HTML")}
    enrichment_labels = {"model": t("اكتمل بالموديل", "Model-assisted"),
                         "fallback": t("بديل محلي", "Local fallback"),
                         "disabled": t("محلي", "Local only")}
    unavailable = t("غير متاح", "Unavailable")
    source_label = (source.get("name") or source_labels[source["kind"]]) if source else (
        artifact["name"] if artifact else unavailable)
    model_label = report["model"] or (t("فحص محلي", "Local only") if report["schema_version"] == 2 else unavailable)
    unique_count = len({finding["rule"] for finding in report["findings"]})
    parts = [
        f'<!doctype html><html lang="{lang}" dir="{t("rtl","ltr")}"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title} | Basira</title><style>'
        'body{font:16px/1.65 system-ui,sans-serif;color:#17252c;max-width:52rem;margin:3rem auto;padding:0 1.5rem}'
        'h1,h2,h3{line-height:1.3}small{color:#54646d}pre{direction:ltr;text-align:left;white-space:pre-wrap;'
        'overflow-wrap:anywhere;background:#edf3f4;padding:1rem}article{border-top:1px solid #b4c2c4;break-inside:avoid}'
        '</style><main><small>BASIRA</small>'
        f'<h1>{title}</h1><p>{t("التاريخ","Date")} <bdi>{esc(report["created_at"])}</bdi><br>'
        f'{t("المصدر","Source")} <bdi>{esc(source_label)}</bdi><br>'
        f'{t("الموديل","Model")} <bdi>{esc(model_label)}</bdi><br>'
        f'{t("الإثراء","Enrichment")} {enrichment_labels.get(report["enrichment"], unavailable)}</p>',
        f'<h2>{t("الملخص","Summary")}</h2><p>{esc(report["summary_"+lang])}</p>',
        f'<h2>{t("مقاييس التشغيل","Run metrics")}</h2><ul>'
        f'<li>{t("أنواع النتائج","Finding types")} · {unique_count}</li>'
        f'<li>{t("مواضع الأدلة","Evidence locations")} · {len(report["findings"])}</li>'
    ]
    for key, label in [("checksRun", t("القواعد المفحوصة","Checks run")),
                       ("validatedCount", t("الملاحظات المؤكدة","Validated findings")),
                       ("modelCalls", t("طلبات النموذج","Model calls")),
                       ("durationMs", t("المدة بالمللي ثانية","Duration in milliseconds"))]:
        if metrics.get(key) is not None:
            parts.append(f'<li>{label} · {esc(metrics[key])}</li>')
    benchmark = metrics.get("benchmark")
    if benchmark:
        parts.append(f'<li>{t("تطابق العينة المرجعية","Reference fixture matches")} · '
                     f'{esc(benchmark["matched"])} / {esc(benchmark["expected"])} · '
                     f'{t("إضافية","Unexpected")} {esc(benchmark["unexpected"])}</li>')
    parts.append(f'</ul><h2>{t("تغطية القواعد","Rule coverage")}</h2>')
    if report["coverage"] is None:
        parts.append(f'<p>{unavailable}</p>')
    else:
        labels = {
            "matched": t("مطابق", "Matched"), "clear": t("سليم", "Clear"),
            "not_applicable": t("غير منطبق", "Not applicable"), "skipped": t("متخطى", "Skipped"),
            "error": t("تعذّر", "Error"),
        }
        parts.append("<ul>")
        for item in report["coverage"]:
            parts.append(f'<li><bdi>{esc(item["rule"])}</bdi> · {labels[item["status"]]} '
                         f'· {item["match_count"]}</li>')
        parts.append("</ul>")
    parts.append(f'<h2>{t("النتائج والأدلة","Findings and evidence")}</h2>')
    severity_labels = {"high":"عالية", "medium":"متوسطة", "low":"منخفضة"}
    for finding in report["findings"]:
        name = finding.get("title_ar" if ar else "title") or finding["rule"]
        advice = finding.get("remediation_ar" if ar else "remediation") or finding["remediation"]
        severity = finding["severity"]
        parts.append(f'<article><h3>{esc(name)}</h3><small>{esc(finding["rule"])} · '
                     f'{esc(severity_labels.get(severity, severity) if ar else severity)} · '
                     f'{esc(finding["path"]) + " · " if finding.get("path") else ""}'
                     f'{t("السطر","Line")} {esc(finding["line"])}</small>'
                     f'<pre><code>{esc(finding["evidence"])}</code></pre><p>{esc(advice)}</p></article>')
    if not report["findings"]:
        if report["coverage"] and all(row["status"] == "not_applicable" for row in report["coverage"]):
            message = t("لم تنطبق أي قاعدة على المصدر.", "No registered rule applied to this source.")
        else:
            message = t("لم تُسجل أدلة مطابقة في التقرير.", "The report contains no matching evidence.")
        parts.append(f'<p>{message}</p>')
    scope_label = (t("مراجعة دفاعية ثابتة للملفات المقدّمة.", "Offline defensive review of the supplied artifacts.")
                   if artifact else t("مراجعة ثابتة لكود HTML المُدخل.", "Static review of the supplied HTML."))
    parts.append(f'<footer><small>{t("النطاق","Scope")} · {scope_label}</small></footer></main></html>')
    return "".join(parts)


@app.get("/api/reports/{report_id}/download")
def download(report_id: str, request: Request, lang: Literal["en", "ar"] = "en",
             format: Literal["html", "json", "pdf"] = "html"):
    report = load_report(request, report_id)
    if format == "pdf":
        from .report_pdf import pdf_download
        return pdf_download(report, lang)
    if format == "json":
        return JSONResponse(report.model_dump(mode="json"), headers={
            "Content-Disposition": f'attachment; filename="basira-{report_id}.json"',
        })
    return HTMLResponse(report_html(report.model_dump(mode="json"), lang), headers={
        "Content-Disposition": f'attachment; filename="basira-{report_id}-{lang}.html"',
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    })


@app.get("/api/product", include_in_schema=False)
def product_mode():
    return {"personal_projects": personal_projects_enabled()}


@app.get("/", include_in_schema=False)
@app.get("/reports", include_in_schema=False)
@app.get("/reports/{report_id}", include_in_schema=False)
@app.get("/projects", include_in_schema=False)
@app.get("/projects/{project_id}/scans/{scan_id}", include_in_schema=False)
@app.get("/demo", include_in_schema=False)
@app.get("/signin", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
@app.get("/scans", include_in_schema=False)
@app.get("/findings", include_in_schema=False)
@app.get("/settings", include_in_schema=False)
@app.get("/new-scan", include_in_schema=False)
def frontend_page(request: Request):
    page = FileResponse(ROOT / "frontend" / "dist" / "index.html", headers={"Cache-Control": "no-store"})
    if personal_projects_enabled():
        return page
    _, token = session(request)
    return set_session(page, token, request)


from .identity import install_identity
from .platform_api import router as platform_router
from .evidence_links import router as evidence_links_router
from .github_import import router as github_import_router
from .model_connections import account_router as account_model_router, router as model_connection_router
from .personal_projects import router as personal_project_router
from .personal_github import router as personal_github_router
from .personal_intake import router as personal_intake_router

install_identity(app)
app.include_router(platform_router)
app.include_router(evidence_links_router)
app.include_router(github_import_router)
app.include_router(model_connection_router)
app.include_router(account_model_router)
app.include_router(personal_project_router)
app.include_router(personal_github_router)
app.include_router(personal_intake_router)
app.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True, check_dir=False), name="frontend")
