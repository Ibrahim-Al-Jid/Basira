"""Provider adapters: one small interface over OpenRouter, OpenAI, Anthropic and Google Gemini.

Pure functions that build requests and parse responses, so the transport (and the key store) stay
elsewhere and every adapter can be tested without a network. Endpoints and headers follow each
provider's public API reference; Anthropic and Gemini request shapes were not called live in this repository.
"""
from typing import Literal

CostClass = Literal["free", "paid", "unknown"]
ANTHROPIC_VERSION = "2023-06-01"

PROVIDERS = {
    "openrouter": {"name": "OpenRouter", "base": "https://openrouter.ai/api/v1", "has_free_path": True},
    "openai": {"name": "OpenAI", "base": "https://api.openai.com/v1", "has_free_path": False},
    "anthropic": {"name": "Anthropic", "base": "https://api.anthropic.com/v1", "has_free_path": False},
    "google": {"name": "Google Gemini", "base": "https://generativelanguage.googleapis.com/v1beta", "has_free_path": False},
}
DEFAULT_PROVIDER = "openrouter"


def public_providers():
    return [{"id": key, "name": value["name"], "free_path": value["has_free_path"]} for key, value in PROVIDERS.items()]


def _headers(provider, key):
    if provider in ("openrouter", "openai"):
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if provider == "anthropic":
        return {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "Content-Type": "application/json"}
    return {"x-goog-api-key": key, "Content-Type": "application/json"}


def _known(provider):
    if provider not in PROVIDERS:
        raise ValueError("Unknown provider")
    return PROVIDERS[provider]["base"]


def models_request(provider, key):
    base = _known(provider)
    url = base + ("/models/user" if provider == "openrouter" else "/models")
    return {"method": "GET", "url": url, "headers": _headers(provider, key)}


def _price_is_zero(value):
    try:
        return float(value) == 0
    except (TypeError, ValueError):
        return False


def parse_models(provider, payload):
    """Return [{id, name, cost}] sorted free first, then by id. Unknown shapes yield an empty list."""
    rows = []
    if not isinstance(payload, dict):
        return rows
    if provider == "google":
        for item in payload.get("models") or []:
            if "generateContent" in (item.get("supportedGenerationMethods") or []):
                model = str(item.get("name", "")).removeprefix("models/")
                rows.append({"id": model, "name": item.get("displayName") or model, "cost": "unknown"})
    else:
        for item in payload.get("data") or []:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            cost: CostClass = "paid"
            if provider == "openrouter":
                price = item.get("pricing") or {}
                cost = "free" if _price_is_zero(price.get("prompt")) and _price_is_zero(price.get("completion")) else "paid"
            rows.append({"id": item["id"], "name": item.get("display_name") or item.get("name") or item["id"], "cost": cost})
    order = {"free": 0, "unknown": 1, "paid": 2}
    return sorted(rows, key=lambda row: (order[row["cost"]], row["id"]))


def cost_warning(provider, model):
    """Text the UI must show, and require acknowledgement of, before a non-free model is saved."""
    if model["cost"] == "free":
        return None
    name = PROVIDERS[provider]["name"]
    if model["cost"] == "unknown":
        return f"{name} may charge for this model after any free allowance. Check your {name} billing before continuing."
    return f"{model['id']} is a paid model. Calls are billed to your {name} account."


def chat_request(provider, key, model, system, user, max_tokens=1200):
    base = _known(provider)
    headers = _headers(provider, key)
    if provider == "anthropic":
        body = {"model": model, "max_tokens": max_tokens, "temperature": 0, "system": system,
                "messages": [{"role": "user", "content": user}]}
        return {"method": "POST", "url": base + "/messages", "headers": headers, "body": body}
    if provider == "google":
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens}}
        return {"method": "POST", "url": f"{base}/models/{model}:generateContent", "headers": headers, "body": body}
    body = {"model": model, "temperature": 0, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    return {"method": "POST", "url": base + "/chat/completions", "headers": headers, "body": body}


def parse_chat(provider, payload):
    """Return the reply text, or an empty string for any unexpected shape."""
    try:
        if provider == "anthropic":
            return "".join(part.get("text", "") for part in payload["content"] if part.get("type") == "text")
        if provider == "google":
            return "".join(part.get("text", "") for part in payload["candidates"][0]["content"]["parts"])
        return payload["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""


def mask_key(key):
    """What the UI may show of a saved key: never more than the last four characters."""
    return "" if not key else "*" * 8 + key[-4:] if len(key) > 8 else "*" * len(key)
