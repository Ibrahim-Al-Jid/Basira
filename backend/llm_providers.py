"""Provider adapters: one small interface over OpenRouter, OpenAI, Anthropic and Google Gemini.

Pure functions that build requests and parse responses, so the transport (and the key store) stay
elsewhere and every adapter can be tested without a network. Endpoints and headers follow each
provider's public API reference; Anthropic and Gemini request shapes were not called live in this repository.
"""
import ipaddress
import socket
from typing import Literal
from urllib.parse import urlsplit

CostClass = Literal["free", "paid", "unknown"]
ANTHROPIC_VERSION = "2023-06-01"

PROVIDERS = {
    "openrouter": {"name": "OpenRouter", "base": "https://openrouter.ai/api/v1", "has_free_path": True},
    "openai": {"name": "OpenAI", "base": "https://api.openai.com/v1", "has_free_path": False},
    "anthropic": {"name": "Anthropic", "base": "https://api.anthropic.com/v1", "has_free_path": False},
    "google": {"name": "Google Gemini", "base": "https://generativelanguage.googleapis.com/v1beta", "has_free_path": False},
}
DEFAULT_PROVIDER = "openrouter"


CUSTOM = "custom"
BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home.arpa")


def public_providers():
    rows = [{"id": key, "name": value["name"], "free_path": value["has_free_path"], "custom": False} for key, value in PROVIDERS.items()]
    return rows + [{"id": CUSTOM, "name": "Custom (OpenAI-compatible)", "free_path": False, "custom": True}]


def _public_address(value):
    address = ipaddress.ip_address(value)
    return address.is_global and not address.is_multicast


def custom_base(url, resolver=socket.getaddrinfo):
    """Validate a user-supplied base URL for an OpenAI-compatible provider and return it normalized.

    The server will send the user's API key to this address, so it must be an https URL on the public
    internet: no credentials in the URL, no loopback, private, link-local or internal names. Names are
    resolved here and every address must be public. Callers must repeat the check at request time,
    because DNS can change between validation and use.
    """
    if not isinstance(url, str) or len(url) > 300:
        raise ValueError("Invalid base URL")
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Base URL must be https, without credentials, query or fragment")
    if parts.port not in (None, 443):
        raise ValueError("Only port 443 is allowed")
    if host == "localhost" or host.endswith(BLOCKED_SUFFIXES):
        raise ValueError("Internal host names are not allowed")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            addresses = {item[4][0] for item in resolver(host, 443, type=socket.SOCK_STREAM)}
        except OSError:
            raise ValueError("Base URL host does not resolve") from None
        if not addresses or not all(_public_address(value) for value in addresses):
            raise ValueError("Base URL must resolve to public addresses only")
    else:
        if not _public_address(str(literal)):
            raise ValueError("Base URL must be a public address")
    return f"https://{parts.netloc.lower()}{parts.path.rstrip('/')}"


def pin_request(request, resolver=None):
    """Connect-time check for a custom provider (DNS rebinding). custom_base() resolved the name when the request was
    built, but the HTTP client would resolve it again, and an attacker's DNS can answer differently the second time.
    Resolve once here, require every address to be public, and send the request to one of those addresses. The Host
    header and the TLS server name stay the original host, so the certificate is still checked against the name."""
    resolver = resolver or socket.getaddrinfo
    parts = urlsplit(request["url"])
    host = parts.hostname or ""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return request
    try:
        addresses = sorted({item[4][0] for item in resolver(host, 443, type=socket.SOCK_STREAM)})
    except OSError:
        raise ValueError("Base URL host does not resolve") from None
    if not addresses or not all(_public_address(value) for value in addresses):
        raise ValueError("Base URL must resolve to public addresses only")
    address = ipaddress.ip_address(addresses[0])
    netloc = f"[{address}]" if address.version == 6 else str(address)
    return {**request, "url": parts._replace(netloc=netloc).geturl(), "headers": {**request["headers"], "Host": host},
            "extensions": {"sni_hostname": host}}


def _headers(provider, key):
    if provider in ("openrouter", "openai", CUSTOM):
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if provider == "anthropic":
        return {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "Content-Type": "application/json"}
    return {"x-goog-api-key": key, "Content-Type": "application/json"}


def _known(provider, base_url=None):
    if provider == CUSTOM:
        if not base_url:
            raise ValueError("Custom provider needs a base URL")
        return custom_base(base_url)
    if provider not in PROVIDERS:
        raise ValueError("Unknown provider")
    return PROVIDERS[provider]["base"]


def models_request(provider, key, base_url=None):
    base = _known(provider, base_url)
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
            if provider == CUSTOM:
                cost = "unknown"
            rows.append({"id": item["id"], "name": item.get("display_name") or item.get("name") or item["id"], "cost": cost})
    order = {"free": 0, "unknown": 1, "paid": 2}
    return sorted(rows, key=lambda row: (order[row["cost"]], row["id"]))


def cost_warning(provider, model):
    """Text the UI must show, and require acknowledgement of, before a non-free model is saved."""
    if model["cost"] == "free":
        return None
    name = PROVIDERS[provider]["name"] if provider in PROVIDERS else "this provider"
    if model["cost"] == "unknown":
        return f"{name} may charge for this model after any free allowance. Check your {name} billing before continuing."
    return f"{model['id']} is a paid model. Calls are billed to your {name} account."


def chat_request(provider, key, model, system, user, max_tokens=1200, base_url=None):
    base = _known(provider, base_url)
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
