"""Provider gateway for bounded suggestions over redacted, server-derived facts."""
from base64 import b64encode
from collections import Counter
from decimal import Decimal, InvalidOperation
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

from . import llm_providers
from .artifact_review import EXTENDED_IDS
from .contracts import AgentAdvisory, Severity
from .model_connections import (
    CONNECTION_ID, MAX_OUTPUT_TOKENS, MODEL_ID, OPERATOR_GENERATION, CatalogRequest, Generation, Identifier, ModelName, VerifyRequest,
    configured_model, connections, decrypt_key, encrypt_key, gateway_config, openrouter_secret,
    operator_enabled, vault,
)
from .scan_contracts import ANALYZER_INPUTS
from .platform_db import PlatformUnavailable, platform_session
from .rules import RULES
from .source_adapters import SOURCE_TOOLS

app = FastAPI(title="Basira provider gateway", docs_url=None, redoc_url=None, openapi_url=None)
IDS = frozenset(EXTENDED_IDS) | RULES.keys()
ADVISOR_RULES = IDS | {tool.rule for tool in SOURCE_TOOLS}
ADVISOR_VERSION = "basira-advisor-1"
ADVISOR_EVIDENCE_LIMIT = 12
ADVISOR_HINT_LIMIT = 3
PROVIDER_URL = "https://openrouter.ai/api/v1"
ServiceAuth = Annotated[str | None, Header(alias="Authorization")]
CATALOG_LIMIT = 4 * 1024 * 1024
REPLY_LIMIT = 256 * 1024


def fetch_limited(method, url, limit, **kwargs):
    """httpx.request with a cap on the body, for providers whose address a user chose. A plain request reads the
    whole body into memory, so a hostile endpoint could stream gigabytes inside the timeout."""
    # httpx.stream() has no `extensions` argument, and the TLS server name of a pinned request travels there.
    options = {name: kwargs.pop(name) for name in ("timeout", "trust_env", "verify", "follow_redirects") if name in kwargs}
    with httpx.Client(**options) as client:
        request = client.build_request(method, url, **kwargs)
        response = client.send(request, stream=True)
        try:
            body = bytearray()
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > limit:
                    raise ValueError("Provider response is too large")
            return httpx.Response(response.status_code, request=response.request, content=bytes(body))
        finally:
            response.close()


@app.exception_handler(RequestValidationError)
async def invalid_facts(_request, _error):
    return JSONResponse({"detail": "Invalid provider request"}, status_code=422)


EvidenceLabel = Annotated[str, Field(pattern=r"^e([1-9]|1[0-2])$")]
ToolLabel = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
RuleLabel = Annotated[str, Field(min_length=1, max_length=64)]


class AdvisorObject(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AdvisorEvidence(AdvisorObject):
    id: EvidenceLabel
    rule: RuleLabel
    severity: Severity
    assessment: Literal["observed", "review_required"]


class AdvisorFacts(AdvisorObject):
    input_kind: Literal["repository", "config"]
    tools: list[ToolLabel] = Field(min_length=1, max_length=len(ANALYZER_INPUTS) + len(SOURCE_TOOLS))
    evidence: list[AdvisorEvidence] = Field(min_length=1, max_length=ADVISOR_EVIDENCE_LIMIT)


class PlanningHint(AdvisorObject):
    tool: ToolLabel
    label: Literal["review_tool_coverage", "review_tool_findings"]


class ValidationHint(AdvisorObject):
    evidence: EvidenceLabel
    label: Literal["review_evidence", "review_context"]


class ExplanationHint(AdvisorObject):
    evidence: EvidenceLabel
    label: Literal["read_remediation", "confirm_scope"]


class AdvisorAnswer(AdvisorObject):
    priority: list[RuleLabel] = Field(min_length=1, max_length=len(ADVISOR_RULES))
    planning: list[PlanningHint] = Field(max_length=ADVISOR_HINT_LIMIT)
    validation: list[ValidationHint] = Field(max_length=ADVISOR_HINT_LIMIT)
    explanation: list[ExplanationHint] = Field(max_length=ADVISOR_HINT_LIMIT)


class Facts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection: Literal["openrouter-default"]
    provider: Literal["openrouter", "openai", "anthropic", "google", "custom"] = "openrouter"
    base_url: str | None = Field(None, max_length=300)
    model: ModelName
    org_id: Identifier
    project_id: Identifier
    scan_id: Identifier
    lease: Identifier
    generation: Generation
    source: Literal["account", "organization"] = "organization"
    counts: dict[str, Annotated[int, Field(ge=1, le=100_000)]] = Field(min_length=1, max_length=len(ADVISOR_RULES))
    advisor: AdvisorFacts | None = None


def verify_service(authorization):
    service_secret = os.environ.get("BASIRA_GATEWAY_TOKEN", "")
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
                    "SELECT has_function_privilege('public.basira_model_credential(text,text)', 'EXECUTE') "
                    "AND has_function_privilege('public.basira_start_model_call(text,text,text,text,text,text)', 'EXECUTE')"
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
        return db.execute(sa.text("SELECT public.basira_model_credential(:org_id, :generation)"),
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
    key = credential(body, encryptor)
    if body.provider == "openrouter":
        verify_provider(key, body.model)
    elif body.model not in {row["id"] for row in other_provider_models(body.provider, key, body.base_url)}:
        raise HTTPException(422, "Model is unavailable for this API key")
    ciphertext = encrypt_key(encryptor, key, body.org_id, body.generation)
    response.headers["Cache-Control"] = "no-store"
    return {"ciphertext": b64encode(ciphertext).decode("ascii")}


def credential(body, encryptor):
    if body.api_key is not None:
        return body.api_key.get_secret_value()
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
    return key


def provider_models(key):
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
        return available
    except (ValueError, KeyError, TypeError, RecursionError, httpx.HTTPError):
        raise HTTPException(503, "OpenRouter verification is unavailable") from None


def pinned(provider, request):
    """A custom provider's address is chosen by a user, so it is resolved and checked again at connect time."""
    return llm_providers.pin_request(request) if provider == llm_providers.CUSTOM else request


def extensions(request):
    return {"extensions": request["extensions"]} if "extensions" in request else {}


def other_provider_models(provider, key, base_url=None):
    """Model catalog for OpenAI, Anthropic, Google or a custom provider. Raises 422 for a rejected key
    and 503 when the provider cannot be reached. Redirects are never followed, so a key is only ever
    sent to the address that was validated for this request."""
    try:
        request = pinned(provider, llm_providers.models_request(provider, key, base_url))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    try:
        response = fetch_limited("GET", request["url"], CATALOG_LIMIT, headers=request["headers"], timeout=8.0,
                                 trust_env=False, follow_redirects=False, **extensions(request))
        if response.status_code in (401, 403):
            raise HTTPException(422, "The provider rejected the API key")
        response.raise_for_status()
        rows = llm_providers.parse_models(provider, response.json())
    except (ValueError, KeyError, TypeError, RecursionError, httpx.HTTPError):
        raise HTTPException(503, "Provider verification is unavailable") from None
    if not rows:
        raise HTTPException(503, "The provider returned no usable models")
    return rows


def other_provider_reply(provider, key, model, system, user, base_url=None):
    """One bounded completion from a non-OpenRouter provider; returns the reply text and the usage dict."""
    try:
        request = pinned(provider, llm_providers.chat_request(provider, key, model, system, user, MAX_OUTPUT_TOKENS, base_url))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    try:
        response = fetch_limited("POST", request["url"], REPLY_LIMIT, headers=request["headers"], json=request["body"],
                                 timeout=12.0, trust_env=False, follow_redirects=False, **extensions(request))
        response.raise_for_status()
        payload = response.json()
    except (ValueError, httpx.HTTPError, RecursionError):
        raise HTTPException(502, "Model could not provide a valid order") from None
    return llm_providers.parse_chat(provider, payload), payload.get("usage") if isinstance(payload, dict) else None


def verify_provider(key, model):
    if not any(isinstance(item, dict) and item.get("id") == model for item in provider_models(key)):
        raise HTTPException(422, "Model is unavailable for this API key")


def free_text_model(item):
    price = item.get("pricing")
    if not isinstance(price, dict):
        return False
    try:
        return all(Decimal(str(price.get(field, default))) == 0 for field, default in (
            ("prompt", None), ("completion", None), ("request", 0), ("internal_reasoning", 0),
        ))
    except (InvalidOperation, ValueError):
        return False


@app.post("/models")
def catalog(body: CatalogRequest, response: Response, authorization: ServiceAuth = None):
    verify_service(authorization)
    encryptor = vault()
    if not encryptor:
        raise HTTPException(503, "Credential store is unavailable")
    models = {}
    if body.provider != "openrouter":
        rows = other_provider_models(body.provider, credential(body, encryptor), body.base_url)
        response.headers["Cache-Control"] = "no-store"
        return {"provider": body.provider, "models": [
            {"id": row["id"], "name": row["name"][:160], "free": row["cost"] == "free", "cost": row["cost"],
             "warning": llm_providers.cost_warning(body.provider, row)}
            for row in rows if len(row["id"]) <= 160 and MODEL_ID.fullmatch(row["id"])]}
    for item in provider_models(credential(body, encryptor)):
        if not isinstance(item, dict):
            continue
        model = item.get("id")
        if not isinstance(model, str) or len(model) > 160 or not MODEL_ID.fullmatch(model):
            continue
        architecture = item.get("architecture")
        outputs = architecture.get("output_modalities") if isinstance(architecture, dict) else None
        if isinstance(outputs, list) and "text" not in outputs:
            continue
        name = item.get("name")
        models[model] = {"id": model, "name": name[:160] if isinstance(name, str) and name else model,
                         "free": free_text_model(item)}
    response.headers["Cache-Control"] = "no-store"
    return {"models": sorted(models.values(), key=lambda item: (not item["free"], item["name"].casefold()))}


def local_start_model_call(db, body):
    from . import platform_runtime as store
    from .identity import ROLE_ACTIONS, project_access
    from .model_connections import account_connection, public_connection
    from .platform_db import personal_namespace_id

    row = store.select_scan(db, body.org_id, body.project_id, body.scan_id, lock=True)
    if (not row or row["state"] != "running" or row["lease"] != body.lease
            or not row["lease_until"] or row["lease_until"] <= store.now()
            or not row["source_expires_at"] or row["source_expires_at"] <= store.now()
            or not row["enrichment_reserved_at"] or row["enrichment_started_at"]
            or row["input_meta"].get("connection_generation") != body.generation
            or row["input_meta"].get("connection_model") != body.model
            or row["input_meta"].get("connection_source", "organization") != body.source):
        return None
    actor = project_access(db, body.project_id, row["user_id"])
    if not actor or actor.org_id != body.org_id or "scan" not in ROLE_ACTIONS[actor.role]:
        return None
    _, policy = store.project_policy(db, body.org_id, body.project_id)
    if body.source == "account":
        current = account_connection(db, row["user_id"])
        namespace = personal_namespace_id(db, row["user_id"])
    else:
        current = public_connection(db, body.org_id, policy)
        namespace = body.org_id
    if not current or current["model"] != body.model or current["generation"] != body.generation:
        return None
    result = db.execute(store.scans.update().where(
        store.scans.c.id == body.scan_id, store.scans.c.enrichment_started_at.is_(None),
    ).values(enrichment_started_at=store.now()))
    if result.rowcount != 1:
        return None
    sealed = sealed_credential(db, namespace, body.generation)
    return (sealed, namespace) if body.source == "account" else (sealed,)


def start_model_call(body):
    try:
        with platform_session() as db:
            if db.bind.dialect.name == "postgresql":
                procedure = "basira_start_account_model_call" if body.source == "account" else "basira_start_model_call"
                return db.execute(sa.text(
                    f"SELECT * FROM public.{procedure}("
                    ":org_id, :project_id, :scan_id, :lease, :generation, :model)"
                ), body.model_dump(exclude={"counts", "connection", "source", "advisor", "provider", "base_url"})).one_or_none()
            return local_start_model_call(db, body)
    except (PlatformUnavailable, sa.exc.SQLAlchemyError):
        raise HTTPException(503, "Scan provider reservation is unavailable") from None


@app.post("/priority")
def priority(body: Facts, authorization: ServiceAuth = None):
    verify_service(authorization)
    allowed_rules = ADVISOR_RULES if body.advisor else IDS
    if not set(body.counts) <= allowed_rules:
        raise HTTPException(422, "Unsupported rule identifier")
    if body.advisor and not valid_advisor_facts(body.advisor, body.counts):
        raise HTTPException(422, "Unsupported advisor facts")
    operator = body.generation == OPERATOR_GENERATION
    if operator and body.source == "account":
        raise HTTPException(409, "Personal connection is no longer available")
    if operator and operator_enabled(body.org_id) != body.model:
        raise HTTPException(409, "Operator connection is no longer available")
    encryptor = None if operator else vault()
    if not operator and not encryptor:
        raise HTTPException(503, "Credential store is unavailable")
    started = start_model_call(body)
    if started is None:
        raise HTTPException(409, "Scan provider reservation was revoked or used")
    namespace = started[1] if body.source == "account" else body.org_id
    key = openrouter_secret() if operator else decrypt_key(encryptor, started[0], namespace, body.generation)
    if not key:
        raise HTTPException(503, "Model enrichment is unavailable")
    if body.provider != "openrouter":
        return other_provider_order(body.provider, key, body.model, body.counts, body.base_url, body.advisor)
    if body.advisor:
        return provider_order(key, body.model, body.counts, advisor=body.advisor)
    return provider_order(key, body.model, body.counts)


ADVISOR_PROMPT = (
    "Prioritize the listed rule IDs and suggest what a human should review for this static report. "
    "Use only the IDs from the input. Never invent tools, findings, explanations, or instructions. "
    "Return only a JSON object with priority (each rule ID once) and three arrays of up to three unique IDs each: "
    '{"planning":[{"tool":"one supplied tool","label":"review_tool_coverage or review_tool_findings"}],'
    '"validation":[{"evidence":"one supplied evidence ID","label":"review_evidence or review_context"}],'
    '"explanation":[{"evidence":"one supplied evidence ID","label":"read_remediation or confirm_scope"}]}. '
    "Use exactly one literal label per entry. Use an empty array when no suggestion is warranted."
)


def allowed_advisor_tools(kind):
    return {tool for tool, inputs in ANALYZER_INPUTS.items() if kind in inputs} | {
        tool.id for tool in SOURCE_TOOLS
    }


def valid_advisor_facts(advisor, counts):
    references = {item.id for item in advisor.evidence}
    observed = Counter(item.rule for item in advisor.evidence)
    return (
        len(advisor.tools) == len(set(advisor.tools))
        and set(advisor.tools) <= allowed_advisor_tools(advisor.input_kind)
        and len(advisor.evidence) == len(references)
        and all(observed[rule] <= counts.get(rule, 0) for rule in observed)
    )


def advisor_answer(payload, counts, advisor):
    answer = AdvisorAnswer.model_validate(payload)
    references = {item.id for item in advisor.evidence}
    groups = (
        ([item.tool for item in answer.planning], set(advisor.tools)),
        ([item.evidence for item in answer.validation], references),
        ([item.evidence for item in answer.explanation], references),
    )
    if not valid_order(answer.priority, counts) or any(
        len(set(selected)) != len(selected) or not set(selected) <= allowed for selected, allowed in groups
    ):
        raise ValueError("Advisor selected a reference outside the verified facts")
    return answer


def provider_order(key, model, counts, *, advisor=None):
    facts = counts if advisor is None else {"counts": counts, **advisor.model_dump()}
    prompt = ADVISOR_PROMPT if advisor else (
        'Order rule IDs by priority. Reply only in JSON: {"priority":["each ID exactly once"]}'
    )
    try:
        response = httpx.post(
            PROVIDER_URL + "/chat/completions", trust_env=False,
            headers={"Authorization": "Bearer " + key}, timeout=12.0,
            json={"model": model, "max_tokens": MAX_OUTPUT_TOKENS,
                  "provider": {"data_collection": "deny", "allow_fallbacks": False},
                  "messages": [
                      {"role": "system", "content": prompt},
                      {"role": "user", "content": json.dumps(facts)},
                  ]},
        )
        response.raise_for_status()
        answer = response.json()
        candidate = json.loads(answer["choices"][0]["message"]["content"])
        if advisor:
            result = advisor_answer(candidate, counts, advisor).model_dump()
        elif not valid_order(candidate["priority"], counts):
            raise ValueError()
        else:
            result = {"priority": candidate["priority"]}
    except (ValueError, KeyError, AttributeError, IndexError, TypeError, RecursionError, httpx.HTTPError):
        raise HTTPException(502, "Model could not provide a valid order") from None
    usage = answer.get("usage")
    observed = {}
    if isinstance(usage, dict):
        for field, dest in (("prompt_tokens", "inputTokens"), ("completion_tokens", "outputTokens")):
            value = usage.get(field)
            if type(value) is int and 0 <= value <= 1_000_000:
                observed[dest] = value
    return {**result, **({"usage": observed} if observed else {})}


def other_provider_order(provider, key, model, counts, base_url, advisor):
    facts = counts if advisor is None else {"counts": counts, **advisor.model_dump()}
    prompt = ADVISOR_PROMPT if advisor else (
        'Order rule IDs by priority. Reply only in JSON: {"priority":["each ID exactly once"]}'
    )
    text, usage = other_provider_reply(provider, key, model, prompt, json.dumps(facts), base_url)
    try:
        candidate = json.loads(text)
        if advisor:
            result = advisor_answer(candidate, counts, advisor).model_dump()
        elif not valid_order(candidate["priority"], counts):
            raise ValueError()
        else:
            result = {"priority": candidate["priority"]}
    except (ValueError, KeyError, AttributeError, TypeError, RecursionError):
        raise HTTPException(502, "Model could not provide a valid order") from None
    observed = {}
    if isinstance(usage, dict):
        for names, dest in ((("prompt_tokens", "input_tokens"), "inputTokens"),
                            (("completion_tokens", "output_tokens"), "outputTokens")):
            value = next((usage[n] for n in names if type(usage.get(n)) is int), None)
            if value is not None and 0 <= value <= 1_000_000:
                observed[dest] = value
    return {**result, **({"usage": observed} if observed else {})}


def valid_order(order, counts):
    return (isinstance(order, list) and len(order) == len(counts)
            and all(isinstance(value, str) for value in order) and set(order) == set(counts))


def advisor_projection(report):
    execution = report.get("execution")
    kind = execution.get("input_kind") if isinstance(execution, dict) else None
    if kind not in {"repository", "config"}:
        return None, {}
    approved = allowed_advisor_tools(kind)
    tools = sorted({row["id"] for row in report.get("tool_selection", [])
                    if row.get("status") == "selected" and row.get("id") in approved})
    if not tools:
        return None, {}
    facts, references = [], {}
    seen = set()
    for item in report["findings"]:
        fingerprint = item.get("fingerprint")
        if (not isinstance(fingerprint, str) or len(fingerprint) != 64
                or any(character not in "0123456789abcdef" for character in fingerprint)
                or fingerprint in seen or item.get("rule") not in ADVISOR_RULES
                or item.get("severity") not in {"high", "medium", "low"}
                or item.get("assessment") not in {"observed", "review_required"}):
            continue
        seen.add(fingerprint)
        reference = f"e{len(facts) + 1}"
        references[reference] = fingerprint
        facts.append(AdvisorEvidence(id=reference, rule=item["rule"], severity=item["severity"],
                                     assessment=item["assessment"]))
        if len(facts) == ADVISOR_EVIDENCE_LIMIT:
            break
    return (AdvisorFacts(input_kind=kind, tools=tools, evidence=facts), references) if facts else (None, {})


def enrich(report, connection, *, org_id, project_id, scan_id, lease, execution_advice=False):
    url, headers = gateway_config()
    advisor, references = advisor_projection(report) if execution_advice else (None, {})
    allowed_rules = ADVISOR_RULES if advisor else IDS
    counts = Counter(item["rule"] for item in report["findings"] if item["rule"] in allowed_rules)
    report["enrichment"] = "fallback"
    if not url or not counts:
        return
    payload = {"counts": counts, "connection": CONNECTION_ID, "model": connection["model"],
               "org_id": org_id, "project_id": project_id, "scan_id": scan_id, "lease": lease,
               "generation": connection["generation"]}
    if connection.get("provider", "openrouter") != "openrouter":
        payload["provider"] = connection["provider"]
        payload["base_url"] = connection.get("base_url")
    if connection.get("source") == "account":
        payload["source"] = "account"
    if advisor:
        payload["advisor"] = advisor.model_dump()
    try:
        reply = httpx.post(url + "/priority", timeout=15, trust_env=False, headers=headers, json=payload)
        if reply.status_code not in (401, 403, 409, 422, 503):
            report["metrics"]["modelCalls"] = 1
        reply.raise_for_status()
        if advisor:
            apply_advice(report, reply.json(), counts, advisor, references)
        else:
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
    record_model_result(report, order, payload.get("usage"))


def apply_advice(report, payload, counts, advisor, references):
    if not isinstance(payload, dict):
        return
    answer = advisor_answer({key: value for key, value in payload.items() if key != "usage"}, counts, advisor)
    report["agent_advisory"] = AgentAdvisory.model_validate({
        "version": ADVISOR_VERSION,
        "planning": [item.model_dump() for item in answer.planning],
        "validation": [{"fingerprint": references[item.evidence], "label": item.label} for item in answer.validation],
        "explanation": [{"fingerprint": references[item.evidence], "label": item.label} for item in answer.explanation],
    }).model_dump()
    record_model_result(report, answer.priority, payload.get("usage"))


def record_model_result(report, order, usage):
    report["priority"] = order
    report["enrichment"] = "model"
    if isinstance(usage, dict):
        for field in ("inputTokens", "outputTokens"):
            if type(usage.get(field)) is int and 0 <= usage[field] <= 1_000_000:
                report["metrics"][field] = usage[field]
