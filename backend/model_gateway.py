"""Provider gateway. Its outbound model request contains rule IDs and counts only."""
from base64 import b64encode
from collections import Counter
import hmac
import json
import os
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import httpx
from pydantic import BaseModel, ConfigDict, Field
import sqlalchemy as sa

from .artifact_review import EXTENDED_IDS
from .model_connections import (
    CONNECTION_ID, MAX_OUTPUT_TOKENS, OPERATOR_GENERATION, Generation, Identifier, ModelName, VerifyRequest,
    configured_model, connections, decrypt_key, encrypt_key, gateway_config, openrouter_secret,
    operator_enabled, vault,
)
from .platform_db import PlatformUnavailable, platform_session
from .rules import RULES

app = FastAPI(title="Marsad provider gateway", docs_url=None, redoc_url=None, openapi_url=None)
IDS = frozenset(EXTENDED_IDS) | RULES.keys()
PROVIDER_URL = "https://openrouter.ai/api/v1"
ServiceAuth = Annotated[str | None, Header(alias="Authorization")]


@app.exception_handler(RequestValidationError)
async def invalid_facts(_request, _error):
    return JSONResponse({"detail": "Invalid provider request"}, status_code=422)


class Facts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection: Literal["openrouter-default"]
    model: ModelName
    org_id: Identifier
    project_id: Identifier
    scan_id: Identifier
    lease: Identifier
    generation: Generation
    counts: dict[str, Annotated[int, Field(ge=1, le=100_000)]] = Field(min_length=1, max_length=len(IDS))


def verify_service(authorization):
    service_secret = os.environ.get("MARSAD_GATEWAY_TOKEN", "")
    actual = (authorization or "").encode("utf-8")
    if not service_secret or not hmac.compare_digest(actual, ("Bearer " + service_secret).encode("utf-8")):
        raise HTTPException(401, "Service authorization required")


@app.get("/health")
def health(authorization: ServiceAuth = None):
    verify_service(authorization)
    model = configured_model()
    return {"ready": bool(model and openrouter_secret()), "model": model}


def store_ready():
    try:
        with platform_session() as db:
            if db.bind.dialect.name == "postgresql":
                return db.scalar(sa.text(
                    "SELECT has_function_privilege('public.marsad_model_credential(text,text)', 'EXECUTE') "
                    "AND has_function_privilege('public.marsad_start_model_call(text,text,text,text,text,text)', 'EXECUTE')"
                )) is True
            db.execute(sa.select(connections.c.org_id).limit(0))
            return True
    except (PlatformUnavailable, sa.exc.SQLAlchemyError):
        return False


@app.get("/managed-health")
def managed_health(authorization: ServiceAuth = None):
    verify_service(authorization)
    return {"ready": bool(vault() and store_ready())}


def sealed_credential(db, org_id, generation):
    if db.bind.dialect.name == "postgresql":
        return db.execute(sa.text("SELECT public.marsad_model_credential(:org_id, :generation)"),
                          {"org_id": org_id, "generation": generation}).scalar_one()
    return db.execute(sa.select(connections.c.ciphertext).where(
        connections.c.org_id == org_id, connections.c.generation == generation,
    )).scalar_one_or_none()


@app.post("/verify")
def verify_connection(body: VerifyRequest, response: Response, authorization: ServiceAuth = None):
    verify_service(authorization)
    encryptor = vault()
    if not encryptor or not store_ready():
        raise HTTPException(503, "Credential store is unavailable")
    if body.api_key is not None:
        key = body.api_key.get_secret_value()
    elif body.previous_generation:
        try:
            with platform_session() as db:
                ciphertext = sealed_credential(db, body.org_id, body.previous_generation)
        except (PlatformUnavailable, sa.exc.SQLAlchemyError):
            raise HTTPException(503, "Credential store is unavailable") from None
        key = decrypt_key(encryptor, ciphertext, body.org_id, body.previous_generation)
        if not key:
            raise HTTPException(409, "Current connection is no longer available")
    else:
        raise HTTPException(422, "An API key is required")
    verify_provider(key, body.model)
    ciphertext = encrypt_key(encryptor, key, body.org_id, body.generation)
    response.headers["Cache-Control"] = "no-store"
    return {"ciphertext": b64encode(ciphertext).decode("ascii")}


def verify_provider(key, model):
    headers = {"Authorization": "Bearer " + key}
    try:
        key_response = httpx.get(PROVIDER_URL + "/key", headers=headers, timeout=5.0, trust_env=False)
        if key_response.status_code in (401, 403):
            raise HTTPException(422, "OpenRouter rejected the API key")
        key_response.raise_for_status()
        profile = key_response.json()["data"]
        if not isinstance(profile, dict):
            raise ValueError("Invalid key response")
        if profile.get("is_management_key") or profile.get("is_provisioning_key"):
            raise HTTPException(422, "An inference API key is required")
        models = httpx.get(PROVIDER_URL + "/models/user", headers=headers, timeout=6.0, trust_env=False)
        if models.status_code in (401, 403):
            raise HTTPException(422, "OpenRouter rejected the API key")
        models.raise_for_status()
        available = models.json()["data"]
        if not isinstance(available, list):
            raise ValueError("Invalid model catalog")
        if not any(isinstance(item, dict) and item.get("id") == model for item in available):
            raise HTTPException(422, "Model is unavailable for this API key")
    except (ValueError, KeyError, TypeError, RecursionError, httpx.HTTPError):
        raise HTTPException(503, "OpenRouter verification is unavailable") from None


def local_start_model_call(db, body):
    from . import platform_runtime as store
    from .identity import ROLE_ACTIONS, project_access
    from .model_connections import public_connection

    row = store.select_scan(db, body.org_id, body.project_id, body.scan_id, lock=True)
    if (not row or row["state"] != "running" or row["lease"] != body.lease
            or not row["lease_until"] or row["lease_until"] <= store.now()
            or not row["source_expires_at"] or row["source_expires_at"] <= store.now()
            or not row["enrichment_reserved_at"] or row["enrichment_started_at"]
            or row["input_meta"].get("connection_generation") != body.generation
            or row["input_meta"].get("connection_model") != body.model):
        return None
    actor = project_access(db, body.project_id, row["user_id"])
    if not actor or actor.org_id != body.org_id or "scan" not in ROLE_ACTIONS[actor.role]:
        return None
    _, policy = store.project_policy(db, body.org_id, body.project_id)
    current = public_connection(db, body.org_id, policy)
    if not current or current["model"] != body.model or current["generation"] != body.generation:
        return None
    result = db.execute(store.scans.update().where(
        store.scans.c.id == body.scan_id, store.scans.c.enrichment_started_at.is_(None),
    ).values(enrichment_started_at=store.now()))
    if result.rowcount != 1:
        return None
    return (sealed_credential(db, body.org_id, body.generation),)


def start_model_call(body):
    try:
        with platform_session() as db:
            if db.bind.dialect.name == "postgresql":
                return db.execute(sa.text(
                    "SELECT * FROM public.marsad_start_model_call("
                    ":org_id, :project_id, :scan_id, :lease, :generation, :model)"
                ), body.model_dump(exclude={"counts", "connection"})).one_or_none()
            return local_start_model_call(db, body)
    except (PlatformUnavailable, sa.exc.SQLAlchemyError):
        raise HTTPException(503, "Scan provider reservation is unavailable") from None


@app.post("/priority")
def priority(body: Facts, authorization: ServiceAuth = None):
    verify_service(authorization)
    if not set(body.counts) <= IDS:
        raise HTTPException(422, "Unsupported rule identifier")
    operator = body.generation == OPERATOR_GENERATION
    if operator and operator_enabled(body.org_id) != body.model:
        raise HTTPException(409, "Operator connection is no longer available")
    encryptor = None if operator else vault()
    if not operator and not encryptor:
        raise HTTPException(503, "Credential store is unavailable")
    started = start_model_call(body)
    if started is None:
        raise HTTPException(409, "Scan provider reservation was revoked or used")
    key = openrouter_secret() if operator else decrypt_key(encryptor, started[0], body.org_id, body.generation)
    if not key:
        raise HTTPException(503, "Model enrichment is unavailable")
    return provider_order(key, body.model, body.counts)


def provider_order(key, model, counts):
    try:
        response = httpx.post(
            PROVIDER_URL + "/chat/completions", trust_env=False,
            headers={"Authorization": "Bearer " + key}, timeout=12.0,
            json={"model": model, "max_tokens": MAX_OUTPUT_TOKENS,
                  "provider": {"data_collection": "deny", "allow_fallbacks": False},
                  "messages": [
                      {"role": "system", "content": "Order rule IDs by priority. Reply only in JSON: "
                                                   '{"priority":["each ID exactly once"]}'},
                      {"role": "user", "content": json.dumps(counts)},
                  ]},
        )
        response.raise_for_status()
        answer = response.json()
        order = json.loads(answer["choices"][0]["message"]["content"])["priority"]
        if not valid_order(order, counts):
            raise ValueError()
    except (ValueError, KeyError, AttributeError, IndexError, TypeError, RecursionError, httpx.HTTPError):
        raise HTTPException(502, "Model could not provide a valid order") from None
    usage = answer.get("usage")
    observed = {}
    if isinstance(usage, dict):
        for field, dest in (("prompt_tokens", "inputTokens"), ("completion_tokens", "outputTokens")):
            value = usage.get(field)
            if type(value) is int and 0 <= value <= 1_000_000:
                observed[dest] = value
    return {"priority": order, **({"usage": observed} if observed else {})}


def valid_order(order, counts):
    return (isinstance(order, list) and len(order) == len(counts)
            and all(isinstance(value, str) for value in order) and set(order) == set(counts))


def enrich(report, connection, *, org_id, project_id, scan_id, lease):
    url, headers = gateway_config()
    counts = Counter(item["rule"] for item in report["findings"] if item["rule"] in IDS)
    report["enrichment"] = "fallback"
    if not url or not counts:
        return
    payload = {"counts": counts, "connection": CONNECTION_ID, "model": connection["model"],
               "org_id": org_id, "project_id": project_id, "scan_id": scan_id, "lease": lease,
               "generation": connection["generation"]}
    try:
        reply = httpx.post(url + "/priority", timeout=15, trust_env=False, headers=headers, json=payload)
        if reply.status_code not in (401, 403, 409, 422, 503):
            report["metrics"]["modelCalls"] = 1
        reply.raise_for_status()
        apply_order(report, reply.json(), counts)
    except httpx.RequestError:
        # A transport failure can happen after the provider started handling the request.
        report["metrics"]["modelCalls"] = None
    except (httpx.HTTPError, KeyError, ValueError, TypeError, RecursionError):
        return

def apply_order(report, payload, counts):
    order = payload["priority"]
    if not valid_order(order, counts):
        return
    position = {rule_id: index for index, rule_id in enumerate(order)}
    report["findings"].sort(key=lambda item: position.get(item["rule"], len(position)))
    report["priority"] = order
    report["enrichment"] = "model"
    usage = payload.get("usage")
    if isinstance(usage, dict):
        for field in ("inputTokens", "outputTokens"):
            if type(usage.get(field)) is int and 0 <= usage[field] <= 1_000_000:
                report["metrics"][field] = usage[field]
