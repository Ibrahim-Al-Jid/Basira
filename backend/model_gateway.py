"""Optional provider service. It accepts registered rule IDs and counts only."""
from collections import Counter
import hmac
import json
import os
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import httpx
from pydantic import BaseModel, ConfigDict, Field

from .artifact_review import EXTENDED_IDS
from .rules import RULES
from .model_connections import CONNECTION_ID, MAX_OUTPUT_TOKENS, configured_model, openrouter_secret

app = FastAPI(title="Marsad provider gateway")
IDS = frozenset(EXTENDED_IDS) | RULES.keys()


@app.exception_handler(RequestValidationError)
async def invalid_facts(_request, _error):
    return JSONResponse({"detail": "Invalid model facts"}, status_code=422)


class Facts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection: Literal["openrouter-default"]
    model: str = Field(min_length=3, max_length=160)
    counts: dict[str, Annotated[int, Field(ge=1, le=100_000)]] = Field(max_length=len(IDS))


def verify_service(authorization):
    service_secret = os.environ.get("MARSAD_GATEWAY_TOKEN", "")
    if not service_secret or not hmac.compare_digest(authorization or "", "Bearer " + service_secret):
        raise HTTPException(401, "Service authorization required")


@app.get("/health")
def health(authorization: Annotated[str | None, Header()] = None):
    verify_service(authorization)
    model = configured_model()
    return {"ready": bool(model and openrouter_secret()), "model": model}


@app.post("/priority")
def priority(body: Facts, authorization: Annotated[str | None, Header()] = None):
    verify_service(authorization)
    key = openrouter_secret()
    model = configured_model()
    if not key or not model or body.model != model:
        raise HTTPException(503, "Model enrichment is unavailable")
    if not set(body.counts) <= IDS:
        raise HTTPException(422, "Unsupported rule identifier")
    return provider_order(key, model, body.counts)


def provider_order(key, model, counts):
    try:
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": "Bearer " + key}, timeout=12.0,
            json={"model": model, "max_tokens": MAX_OUTPUT_TOKENS,
                  "provider": {"data_collection": "deny"},
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


def enrich(report, connection):
    url = os.environ.get("MARSAD_GATEWAY_URL")
    token = os.environ.get("MARSAD_GATEWAY_TOKEN")
    counts = Counter(item["rule"] for item in report["findings"])
    if not url or not token or not counts:
        return
    report["metrics"]["modelCalls"] = 1
    report["enrichment"] = "fallback"
    try:
        reply = httpx.post(url.rstrip("/") + "/priority", timeout=15, trust_env=False,
                           headers={"Authorization": "Bearer " + token}, json={"counts": counts, "connection": CONNECTION_ID, "model": connection["model"]})
        reply.raise_for_status()
        payload = reply.json()
        apply_order(report, payload, counts)
    except (httpx.HTTPError, KeyError, ValueError, TypeError, RecursionError):
        return


def apply_order(report, payload, counts):
    order = payload["priority"]
    if not valid_order(order, counts):
        return
    position = {rule_id: index for index, rule_id in enumerate(order)}
    report["findings"].sort(key=lambda item: position[item["rule"]])
    report["priority"] = order
    report["enrichment"] = "model"
    usage = payload.get("usage")
    if isinstance(usage, dict):
        for field in ("inputTokens", "outputTokens"):
            if type(usage.get(field)) is int and 0 <= usage[field] <= 1_000_000:
                report["metrics"][field] = usage[field]
