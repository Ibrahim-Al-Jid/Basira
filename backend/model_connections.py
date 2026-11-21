"""Server-side project model capability. Public configuration never includes credentials."""
import os
from pathlib import Path
import re

import httpx

CONNECTION_ID = "openrouter-default"
MAX_MODEL_CALLS = 1
MAX_OUTPUT_TOKENS = 1200
MODEL_ID = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.:-]+$")


def configured_model():
    model = os.environ.get("MARSAD_OPENROUTER_MODEL", "")
    return model if len(model) <= 160 and MODEL_ID.fullmatch(model) else None


def public_connection(policy=None):
    model = configured_model()
    if not model or os.environ.get("MARSAD_PROJECT_MODEL_ENABLED") != "1":
        return None
    if policy is not None and policy.get("model_connection") != CONNECTION_ID:
        return None
    return {"id": CONNECTION_ID, "provider": "openrouter", "model": model,
            "max_calls": MAX_MODEL_CALLS, "max_output_tokens": MAX_OUTPUT_TOKENS}


def openrouter_secret():
    """Resolve a gateway-only file each time so replacement and removal take effect."""
    path = os.environ.get("MARSAD_OPENROUTER_KEY_FILE")
    try:
        if path:
            with Path(path).open(encoding="ascii") as source:
                raw = source.read(4097)
        else:
            raw = os.environ.get("MARSAD_OPENROUTER_KEY", "")
    except (OSError, UnicodeError):
        return None
    value = raw.strip()
    if len(raw) <= 4096 and value and all(33 <= ord(char) <= 126 for char in value):
        return value
    return None


def connection_is_ready(connection):
    url = os.environ.get("MARSAD_GATEWAY_URL")
    token = os.environ.get("MARSAD_GATEWAY_TOKEN")
    if not connection or not url or not token:
        return False
    try:
        response = httpx.get(url.rstrip("/") + "/health", timeout=1.5, trust_env=False,
                             headers={"Authorization": "Bearer " + token})
        response.raise_for_status()
        status = response.json()
        return status.get("ready") is True and status.get("model") == connection["model"]
    except (httpx.HTTPError, ValueError, AttributeError):
        return False
