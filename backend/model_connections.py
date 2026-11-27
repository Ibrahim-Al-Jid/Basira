"""Scoped OpenRouter configuration. Credentials never leave the provider gateway in cleartext."""
from base64 import b64decode
from pathlib import Path
import re
import os
from typing import Annotated, Literal
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, HTTPException, Request, Response
import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .identity import LOCAL_HOSTS, MANAGERS, require_membership, require_user
from .platform_db import (
    Base, Membership, Organization, User, personal_namespace_id, personal_projects_enabled, platform_session, utc_now,
)

CONNECTION_ID = "openrouter-default"
MAX_MODEL_CALLS = 1
SEALED_MAX = 284
MAX_OUTPUT_TOKENS = 1200
WINDOW_SECONDS = 600
MAX_ATTEMPTS = 6
OPERATOR_GENERATION = "operator"
MODEL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$"
MODEL_ID = re.compile(MODEL_PATTERN)
Identifier = Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
Generation = Identifier | Literal["operator"]
ModelName = Annotated[str, Field(min_length=3, max_length=160, pattern=MODEL_PATTERN)]
router = APIRouter(prefix="/api/platform/organizations/{org_id}/model-connection",
                   tags=["Organization model connection"])
account_router = APIRouter(prefix="/api/platform/account/model-connection", tags=["Account model connection"])

connections = sa.Table(
    "organization_model_connections", Base.metadata,
    sa.Column("org_id", sa.String(32), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("generation", sa.String(32), nullable=False),
    sa.Column("grant_id", sa.String(32), nullable=False),
    sa.Column("model", sa.String(160), nullable=False),
    sa.Column("provider", sa.String(32), nullable=False, server_default="openrouter"),
    sa.Column("base_url", sa.String(300)),
    sa.Column("ciphertext", sa.LargeBinary, nullable=False),
    sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
)
limits = sa.Table(
    "organization_model_attempts", Base.metadata,
    sa.Column("org_id", sa.String(32), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("window", sa.BigInteger, nullable=False),
    sa.Column("attempts", sa.Integer, nullable=False),
)


ProviderId = Literal["openrouter", "openai", "anthropic", "google", "custom"]


class CatalogKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr | None = Field(None, min_length=8, max_length=256)
    provider: ProviderId = "openrouter"
    base_url: str | None = Field(None, max_length=300)

    @model_validator(mode="after")
    def validate_provider(self):
        if (self.provider == "custom") != bool(self.base_url):
            raise ValueError("A base URL is required for a custom provider and only for a custom provider")
        return self

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, key):
        if key is not None and not re.fullmatch(r"[A-Za-z0-9_.-]+", key.get_secret_value()):
            raise ValueError("Invalid API key")
        return key


class ConnectionWrite(CatalogKey):
    model: ModelName


class VerifyRequest(ConnectionWrite):
    org_id: Identifier
    previous_generation: Identifier | None
    generation: Identifier


class CatalogRequest(CatalogKey):
    org_id: Identifier
    previous_generation: Identifier | None


def configured_model():
    model = os.environ.get("BASIRA_OPENROUTER_MODEL", "")
    return model if len(model) <= 160 and MODEL_ID.fullmatch(model) else None


def operator_enabled(org_id):
    allowed = {value.strip() for value in os.environ.get("BASIRA_OPERATOR_MODEL_ORGS", "").split(",") if value.strip()}
    model = configured_model()
    return model if org_id in allowed and os.environ.get("BASIRA_PROJECT_MODEL_ENABLED") == "1" else None


def openrouter_secret():
    """Resolve the operator file in the gateway so replacement and removal take effect."""
    path = os.environ.get("BASIRA_OPENROUTER_KEY_FILE")
    try:
        if path:
            with Path(path).open(encoding="ascii") as source:
                raw = source.read(4097)
        else:
            raw = os.environ.get("BASIRA_OPENROUTER_KEY", "")
    except (OSError, UnicodeError):
        return None
    value = raw.strip()
    if len(raw) <= 4096 and value and all(33 <= ord(char) <= 126 for char in value):
        return value
    return None


def vault():
    path = os.environ.get("BASIRA_MODEL_MASTER_KEY_FILE")
    if path:
        try:
            with Path(path).open("rb") as source:
                encoded = source.read(128).strip()
            key = b64decode(encoded, altchars=b"-_", validate=True)
            return AESGCM(key) if len(key) == 32 else None
        except (OSError, ValueError):
            pass
    return None


def associated_data(org_id, generation):
    return f"basira:openrouter:v1:{org_id}:{generation}".encode("ascii")


def encrypt_key(encryptor, key, org_id, generation):
    nonce = os.urandom(12)
    return nonce + encryptor.encrypt(nonce, key.encode("ascii"), associated_data(org_id, generation))


def decrypt_key(encryptor, ciphertext, org_id, generation):
    if encryptor and ciphertext and 36 <= len(ciphertext) <= SEALED_MAX:
        try:
            return encryptor.decrypt(ciphertext[:12], ciphertext[12:], associated_data(org_id, generation)).decode("ascii")
        except (InvalidTag, ValueError):
            pass
    return None


def bind_organization(db, org_id):
    if db.bind.dialect.name == "postgresql":
        db.execute(sa.text("SELECT set_config('basira.model_org_id', :org_id, true)"), {"org_id": org_id})


def org_connection(db, org_id):
    bind_organization(db, org_id)
    return db.execute(sa.select(connections.c.generation, connections.c.grant_id, connections.c.model, connections.c.provider,
                              connections.c.base_url, connections.c.verified_at)
                      .where(connections.c.org_id == org_id)).mappings().first()


def connection_info(row, model, grant_id, source):
    if not model:
        return None
    verified = row["verified_at"] if row else None
    if verified and verified.tzinfo is None:
        verified = verified.replace(tzinfo=utc_now().tzinfo)
    return {"id": CONNECTION_ID, "provider": (row["provider"] if row and "provider" in row else None) or "openrouter",
            "base_url": row["base_url"] if row and "base_url" in row else None, "model": model,
            "max_calls": MAX_MODEL_CALLS, "max_output_tokens": MAX_OUTPUT_TOKENS,
            "generation": row["generation"] if row else OPERATOR_GENERATION, "grant_id": grant_id,
            "verified_at": verified, "source": source}


def public_connection(db, org_id, policy=None):
    if personal_projects_enabled():
        return None
    if policy is not None and policy.get("model_connection") != CONNECTION_ID:
        return None
    if db.scalar(sa.select(Organization.personal_owner_id).where(Organization.id == org_id)) is not None:
        return None
    row = org_connection(db, org_id)
    model = row["model"] if row else operator_enabled(org_id)
    grant_id = row["grant_id"] if row else OPERATOR_GENERATION
    if not model or (policy is not None and policy.get("model_grant_id", OPERATOR_GENERATION) != grant_id):
        return None
    return connection_info(row, model, grant_id, "organization" if row else "operator")


def account_connection(db, user_id):
    namespace = personal_namespace_id(db, user_id)
    row = org_connection(db, namespace) if namespace else None
    return connection_info(row, row["model"], row["grant_id"], "account") if row else None


def scan_connection(db, ctx, policy):
    return account_connection(db, ctx.owner_user_id) if ctx.owner_user_id else public_connection(db, ctx.org_id, policy)


def gateway_config():
    url = os.environ.get("BASIRA_GATEWAY_URL")
    token = os.environ.get("BASIRA_GATEWAY_TOKEN")
    return (url.rstrip("/"), {"Authorization": "Bearer " + token}) if url and token else (None, None)


def gateway_status(*, managed=False):
    url, headers = gateway_config()
    if not url:
        return {}
    try:
        response = httpx.get(url + ("/managed-health" if managed else "/health"),
                             timeout=1.5, trust_env=False, headers=headers)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except (httpx.HTTPError, ValueError):
        return {}


def connection_is_ready(connection):
    if not connection:
        return False
    managed = connection["generation"] != OPERATOR_GENERATION
    status = gateway_status(managed=managed)
    return status.get("ready") is True and (managed or status.get("model") == connection["model"])


def transport_guard(request, response):
    response.headers["Cache-Control"] = "no-store"
    if request.url.scheme != "https" and not (
        request.url.scheme == "http" and request.url.hostname in LOCAL_HOSTS
    ):
        raise HTTPException(403, "استخدم HTTPS أو عنوان التشغيل المحلي.")
    if request.method != "GET" and request.headers.get("origin") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "مصدر الطلب غير مسموح.")


def require_manager(db, org_id, user_id, *, lock=False):
    if db.scalar(sa.select(Organization.personal_owner_id).where(Organization.id == org_id)) is not None:
        raise HTTPException(404, "الاتصال غير متاح.")
    if lock:
        db.execute(sa.select(Organization.id).where(Organization.id == org_id).with_for_update()).first()
        member = db.scalar(sa.select(Membership).join(User, User.id == Membership.user_id).where(
            Membership.org_id == org_id, Membership.user_id == user_id,
            Membership.revoked_at.is_(None), User.disabled_at.is_(None),
        ).with_for_update())
        if member is None:
            raise HTTPException(404, "المؤسسة غير متاحة.")
    else:
        member = require_membership(db, org_id, user_id)
    if member.role not in MANAGERS:
        raise HTTPException(403, "إدارة اتصال الموديل متاحة لمالك المؤسسة أو مديرها.")
    bind_organization(db, org_id)


def reserve_verification(db, org_id):
    window = int(utc_now().timestamp()) // WINDOW_SECONDS
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    query = insert(limits).values(org_id=org_id, window=window, attempts=1)
    return db.execute(query.on_conflict_do_update(
        index_elements=[limits.c.org_id],
        set_={"attempts": sa.case((limits.c.window == window, limits.c.attempts + 1), else_=1),
              "window": window},
        where=sa.or_(limits.c.window != window, limits.c.attempts < MAX_ATTEMPTS),
    ).returning(limits.c.attempts)).scalar_one_or_none() is not None


def connection_view(current, available):
    fields = ("id", "provider", "base_url", "model", "verified_at", "source")
    return {"available": available, "connection": {key: current[key] for key in fields} if current else None}


def verify_at_gateway(org_id, body, previous_generation, generation):
    url, headers = gateway_config()
    if not url:
        raise HTTPException(503, "خدمة إدارة اتصال الموديل غير متاحة.")
    payload = {"org_id": org_id, "model": body.model, "generation": generation,
               "previous_generation": previous_generation, "provider": body.provider, "base_url": body.base_url}
    if body.api_key is not None:
        payload["api_key"] = body.api_key.get_secret_value()
    try:
        reply = httpx.post(url + "/verify", headers=headers, json=payload, timeout=15, trust_env=False)
        if reply.status_code == 422:
            raise HTTPException(422, "المزوّد رفض المفتاح أو الموديل المطلوب.")
        if reply.status_code == 409:
            raise HTTPException(409, "الاتصال اتغيّر. حدّث الصفحة وجرّب تاني.")
        reply.raise_for_status()
        ciphertext = b64decode(reply.json()["ciphertext"], validate=True)
        if not 36 <= len(ciphertext) <= SEALED_MAX:
            raise ValueError("Invalid encrypted credential")
        return ciphertext
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        raise HTTPException(503, "تعذّر التحقق من اتصال الموديل. جرّب مرة تانية.") from None


@router.get("")
def read_connection(org_id: Identifier, request: Request, response: Response):
    transport_guard(request, response)
    user = require_user(request)
    with platform_session() as db:
        require_manager(db, org_id, user.id)
        current = public_connection(db, org_id)
    return connection_view(current, gateway_status(managed=True).get("ready") is True)


@router.put("")
def write_connection(org_id: Identifier, body: ConnectionWrite, request: Request, response: Response):
    transport_guard(request, response)
    user = require_user(request)
    return save_connection(body, lambda db: manager_namespace(db, org_id, user.id))


def manager_namespace(db, org_id, user_id):
    require_manager(db, org_id, user_id, lock=True)
    return org_id


def require_same_target(current, body):
    """A stored key is only reused for the provider and address it was verified against."""
    if body.api_key is None and current and (current["provider"] != body.provider or current["base_url"] != body.base_url):
        raise HTTPException(422, "غيّرت المزوّد أو العنوان. أدخل المفتاح من جديد.")


def save_connection(body, locked_namespace, *, source="organization"):
    with platform_session() as db:
        org_id = locked_namespace(db)
        current = org_connection(db, org_id)
        if current is None and body.api_key is None:
            raise HTTPException(422, "أدخل مفتاح المزوّد لإعداد الاتصال.")
        require_same_target(current, body)
        allowed = reserve_verification(db, org_id)
    if not allowed:
        raise HTTPException(429, "عدد محاولات التحقق وصل للحد المؤقت.",
                            headers={"Retry-After": str(WINDOW_SECONDS)})
    old_generation = current["generation"] if current else None
    same_provider = bool(current) and current["provider"] == body.provider and current["base_url"] == body.base_url
    new_generation = old_generation if same_provider and body.api_key is None and body.model == current["model"] else uuid4().hex
    ciphertext = verify_at_gateway(org_id, body, old_generation, new_generation)
    with platform_session() as db:
        if locked_namespace(db) != org_id:
            raise HTTPException(409, "الاتصال اتغيّر. حدّث الصفحة وجرّب تاني.")
        existing = org_connection(db, org_id)
        if (existing["generation"] if existing else None) != old_generation:
            raise HTTPException(409, "الاتصال اتغيّر. حدّث الصفحة وجرّب تاني.")
        values = {"generation": new_generation, "model": body.model, "provider": body.provider, "base_url": body.base_url,
                  "grant_id": existing["grant_id"] if existing else new_generation,
                  "ciphertext": ciphertext, "verified_at": utc_now()}
        if existing:
            db.execute(connections.update().where(connections.c.org_id == org_id).values(**values))
        else:
            db.execute(connections.insert().values(org_id=org_id, **values))
        return connection_view(connection_info(values, body.model, values["grant_id"], source), True)


@router.delete("")
def delete_connection(org_id: Identifier, request: Request, response: Response):
    transport_guard(request, response)
    user = require_user(request)
    with platform_session() as db:
        require_manager(db, org_id, user.id, lock=True)
        db.execute(connections.delete().where(connections.c.org_id == org_id))
        current = public_connection(db, org_id)
    return connection_view(current, gateway_status(managed=True).get("ready") is True)


def account_actor(request, response):
    if not personal_projects_enabled():
        raise HTTPException(404, "المسار غير متاح.")
    transport_guard(request, response)
    return require_user(request).id


def locked_account_namespace(db, user_id):
    namespace = personal_namespace_id(db, user_id, create=True)
    if not namespace:
        raise HTTPException(401, "الحساب غير متاح.")
    return namespace


@account_router.get("")
def read_account_connection(request: Request, response: Response):
    user_id = account_actor(request, response)
    with platform_session() as db:
        current = account_connection(db, user_id)
    return connection_view(current, gateway_status(managed=True).get("ready") is True)


@account_router.post("/models")
def list_account_models(body: CatalogKey, request: Request, response: Response):
    user_id = account_actor(request, response)
    url, headers = gateway_config()
    if not url:
        raise HTTPException(503, "خدمة إدارة اتصال الموديل غير متاحة.")
    with platform_session() as db:
        namespace = locked_account_namespace(db, user_id)
        current = org_connection(db, namespace)
        if not body.api_key and not current:
            raise HTTPException(422, "أدخل مفتاح المزوّد لعرض الموديلات.")
        require_same_target(current, body)
        allowed = reserve_verification(db, namespace)
    if not allowed:
        raise HTTPException(429, "عدد محاولات التحقق وصل للحد المؤقت.",
                            headers={"Retry-After": str(WINDOW_SECONDS)})
    payload = {"org_id": namespace, "previous_generation": current["generation"] if current else None,
               "provider": body.provider, "base_url": body.base_url}
    if body.api_key is not None:
        payload["api_key"] = body.api_key.get_secret_value()
    try:
        reply = httpx.post(url + "/models", headers=headers, json=payload, timeout=15, trust_env=False)
        if reply.status_code == 422:
            raise HTTPException(422, "المزوّد رفض المفتاح. استخدم مفتاح API مخصص للاستدلال.")
        if reply.status_code == 409:
            raise HTTPException(409, "الاتصال اتغيّر. حدّث الصفحة وجرّب تاني.")
        reply.raise_for_status()
        return reply.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "تعذّر تحميل موديلات المزوّد.") from None


@account_router.put("")
def write_account_connection(body: ConnectionWrite, request: Request, response: Response):
    user_id = account_actor(request, response)
    return save_connection(body, lambda db: locked_account_namespace(db, user_id), source="account")


@account_router.delete("")
def delete_account_connection(request: Request, response: Response):
    user_id = account_actor(request, response)
    with platform_session() as db:
        namespace = locked_account_namespace(db, user_id)
        bind_organization(db, namespace)
        db.execute(connections.delete().where(connections.c.org_id == namespace))
    return connection_view(None, gateway_status(managed=True).get("ready") is True)
