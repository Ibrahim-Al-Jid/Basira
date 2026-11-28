"""Normalize the three personal-project sources before queuing offline analysis."""

import asyncio
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from tempfile import SpooledTemporaryFile
from threading import BoundedSemaphore
from typing import Annotated, Literal
from urllib.parse import unquote

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from .analysis_mode import AnalysisMode, MODES, ModeUnavailable
from . import github_import, intake_website, personal_github, platform_runtime as store
from .artifact_review import MAX_ARTIFACT, InputError, prepare, redact_label, safe_path
from .identity import require_project
from .intake_storage import StorageUnavailable, bounded_update, quarantine
from .scan_contracts import DEFAULT_INPUTS, Identifier, ModelConnection, TargetProfile, json_digest
from .platform_db import PersonalGitHubGrant, bind_project_context, platform_session

router = APIRouter(prefix="/api/platform/projects/{project_id}/intake", tags=["Personal intake"])
SLOTS = BoundedSemaphore(4)
WEBSITE_SLOTS = BoundedSemaphore(1)
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)]


class ScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_version: int = Field(ge=0)
    acknowledge_scope: Literal[True]
    model_connection: ModelConnection | None = None
    analysis_mode: AnalysisMode | None = None  # omitted means "hybrid"; see analysis_mode.DEFAULT_MODE


class GitHubRequest(ScopeRequest):
    source: Literal["github"]
    installation_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$")
    repository_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$")
    ref: str = Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._/-]*$")


class WebsiteRequest(ScopeRequest):
    source: Literal["website"]
    url: str = Field(min_length=1, max_length=250)


def owner_context(request, project_id):
    ctx = require_project(request, project_id, "scan")
    if not ctx.owner_user_id:
        raise HTTPException(404, "المسار متاح للمشاريع الشخصية.")
    return ctx


def preflight(ctx, scope_version, key, digest=None, url=None):
    ids = {"org_id": ctx.org_id, "project_id": ctx.project_id}
    with platform_session() as db:
        bind_project_context(db, ctx)
        scoped = store.scope(store.scans, **ids)
        own = store.scans.c.user_id == ctx.user_id
        existing = db.execute(select(store.scans).where(
            scoped, own, store.scans.c.idempotency_key == key,
        )).mappings().first()
        if existing:
            if digest is None:
                return None  # ZIP retries must first verify the uploaded bytes.
            if existing["request_digest"] != digest:
                raise HTTPException(409, "المفتاح ده مرتبط بطلب مختلف.")
            return store.scan_view(existing)
        version, policy = store.project_policy(db, **ids)
        if ((scope_version is not None and version != scope_version)
                or "repository" not in policy.get("allowed_kinds", DEFAULT_INPUTS)):
            raise HTTPException(409, "راجع سياسة ونطاق المشروع قبل الفحص.")
        configured_origin = store.web_origin(policy.get("base_url"))
        if url and configured_origin and store.web_origin(url) != configured_origin:
            raise HTTPException(409, "عنوان الصفحة خارج نطاق المشروع.")
        pending = db.scalar(select(func.count()).select_from(store.scans).where(
            scoped, store.scans.c.state.in_(("queued", "running")),
        ))
        recent = db.scalar(select(func.count()).select_from(store.scans).where(
            scoped, own, store.scans.c.created_at > store.now() - timedelta(minutes=1),
        ))
        if pending >= 10 or recent >= 8:
            raise busy()
    return None


def busy():
    return HTTPException(429, "وصل جمع الأدلة للحد المؤقت. حاول بعد دقيقة.", headers={"Retry-After": "60"})


def archive_snapshot(file, size, digest, mode, name):
    with quarantine(file, size, digest) as staged:
        if staged.read(4) != b"PK\x03\x04":
            raise InputError("الملف لازم يكون ZIP صالح.")
        staged.seek(0)
        metrics = {}
        files, _, _, manifest = prepare("repository", name, staged, archive_metrics=metrics)
        paths = [PurePosixPath(path.lower()) for path in files]
        roots = {path.parent for path in paths if path.name in {
            "package.json", "pyproject.toml", "requirements.txt", "cargo.toml", "go.mod", "pom.xml", "gemfile",
        }}
        profile = TargetProfile(
            mode=mode, text_files=len(files), skipped_files=len(manifest) - len(files),
            expanded_text_bytes=sum(len(value.encode()) for value in files.values()),
            expanded_text_sha256=json_digest(files),
            file_types=sorted({path.suffix for path in paths if path.suffix}),
            root_count=max(1, len(roots)),
            executable_entries=metrics["executable_entries"],
            lockfiles=sum(path.name.endswith(".lock") or path.name in {
                "package-lock.json", "npm-shrinkwrap.json", "go.sum", "pnpm-lock.yaml",
            } for path in paths),
            config_files=sum(path.suffix in {".ini", ".toml", ".conf", ".yaml", ".yml", ".env"}
                             or path.name.startswith((".env", "dockerfile")) for path in paths),
            api_specs=sum(path.stem in {"openapi", "swagger"} for path in paths),
        )
        staged.seek(0)
        return staged.read(), profile


def commit_scan(ctx, scope, key, digest, raw, name, profile, *, github=None, before_create=None):
    envelope = {"kind": "har" if profile.mode == "website" else "repository", "name": name,
                "bytes": len(raw), "profile": profile.model_dump(exclude_none=True)}
    if github:
        envelope["github"] = github
    try:
        return store.create_scan(ctx, envelope, raw, key, scope_version=scope.scope_version,
                                 model_connection=scope.model_connection, before_create=before_create,
                                 target_reference=store.web_origin(profile.public_url), intake_digest=digest,
                                 analysis_mode=scope.analysis_mode)
    except ModeUnavailable as exc:
        raise HTTPException(422, str(exc)) from None
    except store.Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except store.QueueLimit:
        raise busy() from None


def finish_upload(ctx, scope, key, file, name, digest):
    request_digest = json_digest(["zip", name, digest, scope.model_dump()])
    existing = preflight(ctx, scope.scope_version, key, request_digest)
    if existing:
        return existing
    raw, profile = archive_snapshot(file, file.tell(), digest, "zip", name)
    return commit_scan(ctx, scope, key, request_digest, raw, name, profile)


def compatible_zip(ctx, envelope, raw, key, *, scope_version, model_connection, analysis_mode=None):
    request_digest = store.scan_request_digest(envelope, raw, scope_version, model_connection, analysis_mode=analysis_mode)
    existing = preflight(ctx, scope_version, key, request_digest)
    if existing:
        return existing
    if not SLOTS.acquire(blocking=False):
        raise busy()
    try:
        raw, profile = archive_snapshot(BytesIO(raw), len(raw), sha256(raw).hexdigest(), "zip", envelope["name"])
        return store.create_scan(ctx, {**envelope, "profile": profile.model_dump(exclude_none=True)}, raw, key,
                                 scope_version=scope_version, model_connection=model_connection,
                                 intake_digest=request_digest, analysis_mode=analysis_mode)
    finally:
        SLOTS.release()


@router.post("/zip", status_code=202)
async def upload_zip(
    project_id: Identifier, request: Request, key: Key,
    name_header: Annotated[str, Header(alias="X-Artifact-Name", min_length=1, max_length=2900)],
    scope_version: Annotated[int, Header(alias="X-Scope-Version", ge=0)],
    acknowledge: Annotated[Literal["true"], Header(alias="X-Acknowledge-Scope")],
    model: Annotated[ModelConnection | None, Header(alias="X-Model-Connection")] = None,
    mode: Annotated[str | None, Header(alias="X-Analysis-Mode")] = None,
):
    if mode is not None and mode not in MODES:
        raise HTTPException(422, "X-Analysis-Mode لازم يكون واحد من: rules أو agents أو hybrid.")
    scope = ScopeRequest(scope_version=scope_version, acknowledge_scope=acknowledge == "true",
                         model_connection=model, analysis_mode=mode)
    ctx = await run_in_threadpool(owner_context, request, project_id)
    await run_in_threadpool(preflight, ctx, scope_version, key)
    if request.headers.get("content-type", "").split(";", 1)[0].lower() not in {
        "application/zip", "application/x-zip-compressed", "application/octet-stream",
    }:
        raise HTTPException(415, "نوع ملف الرفع لازم يكون ZIP.")
    try:
        name = unquote(name_header, errors="strict")
        if "/" in name or not name.lower().endswith(".zip"):
            raise InputError("اختار ملف بامتداد ZIP.")
        name = redact_label(safe_path(name))
        if not SLOTS.acquire(blocking=False):
            raise busy()
        try:
            with SpooledTemporaryFile(max_size=256_000) as file:
                digest = sha256()
                async with asyncio.timeout(30):
                    async for block in request.stream():
                        await run_in_threadpool(bounded_update, file, digest, block)
                return await run_in_threadpool(finish_upload, ctx, scope, key, file, name, digest.hexdigest())
        finally:
            SLOTS.release()
    except (InputError, UnicodeError) as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, InputError) else "اسم ملف ZIP غير صالح.") from None
    except (TimeoutError, ClientDisconnect):
        raise HTTPException(408, "رفع ZIP اتقطع أو انتهت مهلته.") from None
    except StorageUnavailable:
        raise HTTPException(503, "تخزين اللقطات غير متاح مؤقتًا.") from None


@router.post("", status_code=202)
def remote_source(project_id: Identifier, body: Annotated[GitHubRequest | WebsiteRequest, Field(discriminator="source")],
                  request: Request, key: Key):
    ctx = owner_context(request, project_id)
    if not SLOTS.acquire(blocking=False):
        raise busy()
    try:
        if isinstance(body, WebsiteRequest):
            url = intake_website.approved_url(body.url, project_id)
            digest = json_digest([body.model_dump(exclude={"url"}), url])
            existing = preflight(ctx, body.scope_version, key, digest, url)
            if existing:
                return existing
            if not WEBSITE_SLOTS.acquire(blocking=False):
                raise busy()
            try:
                raw, facts = intake_website.capture_scope(url, project_id)
            finally:
                WEBSITE_SLOTS.release()
            profile = TargetProfile(mode="website", public_url=url, **facts)
            return commit_scan(ctx, body, key, digest, raw, "website-evidence.har", profile)
        digest = json_digest(body.model_dump())
        existing = preflight(ctx, body.scope_version, key, digest)
        if existing:
            return existing
        if any(part in {"", ".", ".."} for part in body.ref.split("/")):
            raise InputError("الفرع أو معرّف النسخة غير صالح.")
        generation, token = personal_github.grant_for(ctx.user_id)
        installation_id, repository_id = int(body.installation_id), int(body.repository_id)
        if max(installation_id, repository_id) > github_import.MAX_INSTALLATION:
            raise InputError("معرّف GitHub خارج النطاق المدعوم.")
        repo, commit, raw = github_import.provider_call(
            personal_github.fetch_snapshot, token, installation_id, repository_id, body.ref,
        )
        name = f"github-{commit[:12]}.zip"
        raw, profile = archive_snapshot(BytesIO(raw), len(raw), sha256(raw).hexdigest(), "github", name)

        def check_grant(db):
            grant = db.get(PersonalGitHubGrant, ctx.user_id, with_for_update=True)
            if not grant or grant.generation != generation or grant.expires_at.replace(tzinfo=None) <= store.now():
                raise store.Conflict("اتصال GitHub اتغيّر قبل تسجيل الفحص.")

        ref = {"repository": repo["repository"], "commit": commit, "connection_id": generation,
               "installation_id": body.installation_id, "repository_id": body.repository_id}
        return commit_scan(ctx, body, key, digest, raw, name, profile, github=ref, before_create=check_grant)
    except InputError as exc:
        raise HTTPException(422, str(exc)) from None
    except StorageUnavailable:
        raise HTTPException(503, "تخزين اللقطات غير متاح مؤقتًا.") from None
    finally:
        SLOTS.release()
