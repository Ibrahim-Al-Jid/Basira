"""Basira's same-origin HTTP API and React frontend."""
import html
from pathlib import Path
import re

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .artifact_review import catalog as rule_catalog
from .taxonomy import public as taxonomy_public
from .platform_db import personal_projects_enabled
from .observability import install_observability

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="Basira Agent Lab", version="2.3")


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


PAGE_POLICY = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
               "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
               "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")


def page_headers(response):
    """Security headers for the single-page app shell; a route's own header wins."""
    if not response.headers.get("content-type", "").startswith("text/html"):
        return response
    response.headers.setdefault("Content-Security-Policy", PAGE_POLICY)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response


@app.middleware("http")
async def protect_requests(request, call_next):
    path = request.url.path.rstrip("/")
    if personal_projects_enabled() and (
        path == "/demo"
        or path.startswith(("/api/platform/organizations/", "/api/platform/invitations/"))
        or path == "/api/platform/organizations"
        or re.match(r"^/api/platform/projects/[^/]+/(?:grants|github-source)(?:/|$)", path)
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
    response = await call_next(request)
    if request.url.path.startswith("/assets/"):
        # Vite emits content-hashed asset names, so a hit can never go stale.
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        return response
    return page_headers(response)


@app.get("/api/catalog")
def security_catalog():
    return rule_catalog()


@app.get("/api/taxonomy")
def vulnerability_taxonomy():
    return taxonomy_public()


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


@app.get("/api/product", include_in_schema=False)
def product_mode():
    return {"personal_projects": personal_projects_enabled()}


@app.get("/", include_in_schema=False)
@app.get("/reports", include_in_schema=False)
@app.get("/reports/{report_id}", include_in_schema=False)
@app.get("/projects", include_in_schema=False)
@app.get("/projects/{project_id}", include_in_schema=False)
@app.get("/projects/{project_id}/scans/{scan_id}", include_in_schema=False)
@app.get("/projects/{project_id}/reports/{report_id}", include_in_schema=False)
@app.get("/demo", include_in_schema=False)
@app.get("/signin", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
@app.get("/scans", include_in_schema=False)
@app.get("/findings", include_in_schema=False)
@app.get("/settings", include_in_schema=False)
@app.get("/new-scan", include_in_schema=False)
def frontend_page(request: Request):
    return FileResponse(ROOT / "frontend" / "dist" / "index.html", headers={"Cache-Control": "no-store"})


from .identity import install_identity
from .platform_api import router as platform_router
from .evidence_links import router as evidence_links_router
from .github_import import router as github_import_router
from .model_connections import account_router as account_model_router, router as model_connection_router
from .personal_projects import router as personal_project_router
from .personal_github import router as personal_github_router
from .personal_intake import router as personal_intake_router

install_identity(app)
install_observability(app)
app.include_router(platform_router)
app.include_router(evidence_links_router)
app.include_router(github_import_router)
app.include_router(model_connection_router)
app.include_router(account_model_router)
app.include_router(personal_project_router)
app.include_router(personal_github_router)
app.include_router(personal_intake_router)
app.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True, check_dir=False), name="frontend")


@app.exception_handler(404)
async def not_found_page(request: Request, exc):
    """Unknown browser URLs open the app's own "Page not found" screen. API calls keep the JSON error."""
    path = request.url.path
    if (request.method == "GET" and not path.startswith(("/api/", "/assets/")) and "text/html" in request.headers.get("accept", "")
            and (ROOT / "frontend" / "dist" / "index.html").is_file()):
        return FileResponse(ROOT / "frontend" / "dist" / "index.html", status_code=404, headers={"Cache-Control": "no-store"})
    return JSONResponse({"detail": getattr(exc, "detail", "Not Found")}, status_code=404)
