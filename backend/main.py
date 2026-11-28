"""Basira's same-origin HTTP API and React frontend."""
import asyncio
import base64
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from functools import lru_cache
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
from . import run_guard
from .taxonomy import public as taxonomy_public
from .platform_db import personal_projects_enabled
from .observability import install_obser        or path.startswith(("/api/reports/", "/api/platform/organizations/", "/api/platform/invitations/"))
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
        return        owner = owner_key(token)
        # Expired rows are never read again; drop them before adding one, so the table
        # tracks live sessions instead of every browser that ever loaded a page.
        db.execute("DELETE FROM sessions WHERE expires_at IS NOT NULL AND expires_at <= ?", (int(time.time()),))
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
                                SELECT i.summary_json, CAS                        filename = redact_label(source.name) or ("basira-sample.html" if source.kind == "sample" else "source.html")
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
                                                                                                                                                                f'<h1>{title}</h1><p>{t("التار        else:
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
                                                                                                                                                                                                                                                                    return JS
