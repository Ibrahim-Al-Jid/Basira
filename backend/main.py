"""Marsad's same-origin HTTP API and React frontend."""
import asyncio
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import html
import json
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr

from .graph import GraphError, run_graph

ROOT = Path(__file__).resolve().parents[1]
COOKIE = "marsad_session"
app = FastAPI(title="Marsad Agent Lab", version="2.0")


class Connect(BaseModel):
    key: SecretStr = Field(min_length=8, max_length=512)


class Run(Connect):
    source: str = Field(min_length=1, max_length=250_000)
    model: str = Field(min_length=1, max_length=200)
    allow_paid: bool = False


@app.exception_handler(RequestValidationError)
async def validation_error(_request, _error):
    # Pydantic's default body may echo a submitted credential or HTML source.
    return JSONResponse({"detail": "راجع المفتاح والموديل وحجم كود HTML."}, status_code=422)


@app.middleware("http")
async def protect_requests(request, call_next):
    if request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if request.method == "POST" and origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "مصدر الطلب غير مسموح."}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    return await call_next(request)


@contextmanager
def database():
    path = Path(os.environ.get("MARSAD_DB_PATH", ROOT / "data" / "marsad.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=5)) as db, db:
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions(owner TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS reports(
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, created_at TEXT NOT NULL,
                model TEXT NOT NULL, finding_count INTEGER NOT NULL, report_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS owner_reports ON reports(owner,created_at DESC);
        """)
        yield db


def owner_key(token):
    return hashlib.sha256(token.encode()).hexdigest()


def session(request):
    token = request.cookies.get(COOKIE, "")
    with database() as db:
        if token and len(token) == 43 and db.execute(
            "SELECT 1 FROM sessions WHERE owner=?", (owner_key(token),)
        ).fetchone():
            return owner_key(token), None
        token = secrets.token_urlsafe(32)
        owner = owner_key(token)
        db.execute("INSERT INTO sessions(owner) VALUES(?)", (owner,))
    return owner, token


def set_session(response, token, request):
    if token:
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict",
                            secure=request.url.scheme == "https", max_age=30 * 86400)
    return response


def zero_text_cost(pricing):
    if not isinstance(pricing, dict) or not {"prompt", "completion"} <= pricing.keys():
        return False
    keys = ("prompt", "completion", "request", "internal_reasoning", "input_cache_read", "input_cache_write")
    try:
        return all(Decimal(str(pricing.get(k, 0))) == 0 for k in keys)
    except (ValueError, InvalidOperation):
        return False


async def catalog(key):
    if any(ord(ch) < 33 or ord(ch) > 126 for ch in key):
        raise HTTPException(422, "صيغة مفتاح OpenRouter غير صالحة.")
    try:
        async with httpx.AsyncClient(base_url="https://openrouter.ai/api/v1/", timeout=15,
                                     headers={"Authorization": f"Bearer {key}"}) as client:
            auth = await client.get("key")
            auth.raise_for_status()
            response = await client.get("models/user")
            response.raise_for_status()
            rows = response.json()["data"]
            models = [
                {"id": row["id"], "name": row.get("name") or row["id"], "free": zero_text_cost(row.get("pricing"))}
                for row in rows
                if isinstance(row.get("id"), str)
                and "text" in (row.get("architecture") or {}).get("output_modalities", ["text"])
                and "text" in (row.get("architecture") or {}).get("input_modalities", ["text"])
                and (not row.get("endpoints") or "/api/v1/chat/completions" in row["endpoints"])
            ]
            return sorted(models, key=lambda m: (not m["free"], m["name"].casefold()))
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        errors = {401: "مفتاح OpenRouter غير صالح.", 403: "OpenRouter رفض الوصول بهذا المفتاح.",
                  429: "وصل الحساب لحد طلبات OpenRouter. حاول لاحقًا."}
        raise HTTPException(status if status in errors else 502,
                            errors.get(status, "تعذّر تحميل قائمة الموديلات من OpenRouter.")) from None
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(502, "تعذّر الاتصال بـOpenRouter أو قراءة قائمة الموديلات.") from None


@app.post("/api/models")
async def models(body: Connect):
    return {"models": await catalog(body.key.get_secret_value())}


def summaries(owner):
    with database() as db:
        rows = db.execute("SELECT id, created_at, model, finding_count FROM reports "
                          "WHERE owner=? ORDER BY created_at DESC LIMIT 100", (owner,))
        return [dict(row) for row in rows]


@app.get("/api/history")
def history(request: Request):
    owner, token = session(request)
    return set_session(JSONResponse({"reports": summaries(owner)}), token, request)


def save_report(owner, report):
    with database() as db:
        db.execute("INSERT INTO reports VALUES(?,?,?,?,?,?)", (
            report["id"], owner, report["created_at"], report["model"], len(report["findings"]),
            json.dumps(report, ensure_ascii=False),
        ))
        db.execute("DELETE FROM reports WHERE owner=? AND id NOT IN "
                   "(SELECT id FROM reports WHERE owner=? ORDER BY created_at DESC LIMIT 100)", (owner, owner))


@app.post("/api/run")
async def run(body: Run, request: Request):
    key = body.key.get_secret_value()
    if "<" not in body.source or ">" not in body.source:
        raise HTTPException(422, "أدخل كود HTML يحتوي على عناصر الصفحة.")
    selected = next((item for item in await catalog(key) if item["id"] == body.model), None)
    if not selected:
        raise HTTPException(422, "الموديل غير متاح حاليًا. حدّث القائمة.")
    if not selected["free"] and not body.allow_paid:
        raise HTTPException(409, "سعر الموديل غير مجاني. حدّث الاختيار قبل التشغيل.")
    owner, token = session(request)
    past = summaries(owner)
    previous = {"findingsCount": past[0]["finding_count"]} if past else None

    async def events():
        queue = asyncio.Queue()
        steps = []

        async def emit(event):
            step = {name: event[name] for name in ("node", "status", "parents", "detail")}
            if key in json.dumps(step, ensure_ascii=False):
                raise RuntimeError("Credential in event")
            steps.append(step)
            await queue.put({"type": "step", **step})

        async def execute():
            try:
                async with asyncio.timeout(300):
                    result = await run_graph(body.source, body.model, key, emit, previous=previous)
                report = {field: result[field] for field in ("findings", "metrics", "summary_ar", "summary_en")}
                report.update(id=uuid4().hex, created_at=datetime.now(timezone.utc).isoformat(),
                              model=body.model, steps=steps)
                if key in json.dumps(report, ensure_ascii=False):
                    raise RuntimeError("Credential in report")
                save_report(owner, report)
                await queue.put({"type": "complete", "report": report})
            except TimeoutError:
                await queue.put({"type": "error", "message": "انتهت مهلة التشغيل. جرّب موديل تاني."})
            except GraphError as exc:
                message = str(exc)
                await queue.put({"type": "error", "message": message if key not in message else "تعذّر إكمال التشغيل."})
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                reason = {401: "OpenRouter رفض المفتاح.", 402: "رصيد OpenRouter غير كافٍ.",
                          429: "وصل الموديل لحد الاستخدام. اختار موديل تاني أو حاول لاحقًا."}
                await queue.put({"type": "error", "message": reason.get(
                    status, "تعذّر استكمال التشغيل. راجع المدخل والموديل وإتاحته ثم أعد المحاولة.")})

        task = asyncio.create_task(execute())
        try:
            while True:
                event = await queue.get()
                yield json.dumps(event, ensure_ascii=False) + "\n"
                if event["type"] != "step":
                    break
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    response = StreamingResponse(events(), media_type="application/x-ndjson",
                                 headers={"X-Accel-Buffering": "no"})
    return set_session(response, token, request)


def load_report(request, report_id):
    token = request.cookies.get(COOKIE, "")
    with database() as db:
        row = db.execute("SELECT report_json FROM reports WHERE id=? AND owner=?",
                         (report_id, owner_key(token))).fetchone()
    if not row:
        raise HTTPException(404, "التقرير غير موجود في الجلسة دي.")
    return json.loads(row[0])


@app.get("/api/reports/{report_id}")
def report_detail(report_id: str, request: Request):
    return load_report(request, report_id)


def report_html(report, lang):
    ar = lang == "ar"
    def t(arabic, english):
        return arabic if ar else english
    def esc(value):
        return html.escape(str(value), quote=True)
    title = t("تقرير مراجعة أمان HTML", "HTML security review")
    metrics = report["metrics"]
    parts = [
        f'<!doctype html><html lang="{lang}" dir="{t("rtl","ltr")}"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title} | Marsad</title><style>'
        'body{font:16px/1.65 system-ui,sans-serif;color:#17252c;max-width:52rem;margin:3rem auto;padding:0 1.5rem}'
        'h1,h2,h3{line-height:1.3}small{color:#54646d}pre{direction:ltr;text-align:left;white-space:pre-wrap;'
        'overflow-wrap:anywhere;background:#edf3f4;padding:1rem}article{border-top:1px solid #b4c2c4;break-inside:avoid}'
        '</style><main><small>MARSAD</small>'
        f'<h1>{title}</h1><p>{t("التاريخ","Date")} <bdi>{esc(report["created_at"])}</bdi><br>'
        f'{t("الموديل","Model")} <bdi>{esc(report["model"])}</bdi></p>',
        f'<h2>{t("الملخص","Summary")}</h2><p>{esc(report["summary_"+lang])}</p>',
        f'<h2>{t("مقاييس التشغيل","Run metrics")}</h2><ul>'
    ]
    for key, label in [("checksRun", t("القواعد المفحوصة","Checks run")),
                       ("validatedCount", t("الملاحظات المؤكدة","Validated findings")),
                       ("modelCalls", t("طلبات النموذج","Model calls")),
                       ("durationMs", t("المدة بالمللي ثانية","Duration in milliseconds"))]:
        if key in metrics:
            parts.append(f'<li>{label} · {esc(metrics[key])}</li>')
    benchmark = metrics.get("benchmark")
    if benchmark:
        parts.append(f'<li>{t("تطابق العينة المرجعية","Reference fixture matches")} · '
                     f'{esc(benchmark["matched"])} / {esc(benchmark["expected"])} · '
                     f'{t("إضافية","Unexpected")} {esc(benchmark["unexpected"])}</li>')
    parts.append(f'</ul><h2>{t("النتائج والأدلة","Findings and evidence")}</h2>')
    severity_labels = {"high":"عالية", "medium":"متوسطة", "low":"منخفضة"}
    for finding in report["findings"]:
        name = finding.get("title_ar" if ar else "title") or finding["rule"]
        advice = finding.get("remediation_ar" if ar else "remediation", "")
        severity = finding["severity"]
        parts.append(f'<article><h3>{esc(name)}</h3><small>{esc(finding["rule"])} · '
                     f'{esc(severity_labels.get(severity, severity) if ar else severity)} · '
                     f'{t("السطر","Line")} {esc(finding["line"])}</small>'
                     f'<pre><code>{esc(finding["evidence"])}</code></pre><p>{esc(advice)}</p></article>')
    if not report["findings"]:
        parts.append(f'<p>{t("لم ترصد القواعد المختارة ملاحظات.","The selected checks found no matching evidence.")}</p>')
    parts.append(f'<footer><small>{t("النطاق: مراجعة ثابتة لكود HTML المُدخل.","Scope: static review of the supplied HTML.")}</small></footer></main></html>')
    return "".join(parts)


@app.get("/api/reports/{report_id}/download")
def download(report_id: str, request: Request, lang: Literal["en", "ar"] = "en"):
    report = load_report(request, report_id)
    return HTMLResponse(report_html(report, lang), headers={
        "Content-Disposition": f'attachment; filename="marsad-{report["id"]}-{lang}.html"',
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    })


app.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True, check_dir=False), name="frontend")
