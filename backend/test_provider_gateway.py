import httpx
import pytest
from fastapi import HTTPException

from . import model_gateway as gateway


def reply(status, data, method="GET", url="https://x.test/"):
    return httpx.Response(status, request=httpx.Request(method, url), json=data)


def test_catalog_for_each_preset_uses_its_own_url_header_and_never_follows_redirects(monkeypatch):
    seen = []

    def fake_get(url, **kwargs):
        seen.append((url, kwargs["headers"], kwargs["follow_redirects"]))
        if "anthropic" in url:
            return reply(200, {"data": [{"id": "claude-x", "display_name": "Claude X"}]})
        if "googleapis" in url:
            return reply(200, {"models": [{"name": "models/gemini-x", "supportedGenerationMethods": ["generateContent"]}]})
        return reply(200, {"data": [{"id": "gpt-x"}]})

    monkeypatch.setattr(gateway.httpx, "get", fake_get)
    for provider, expected in (("openai", "gpt-x"), ("anthropic", "claude-x"), ("google", "gemini-x")):
        assert gateway.other_provider_models(provider, "k-secret")[0]["id"] == expected
    assert all(url.startswith("https://") and "k-secret" not in url and not follow for url, _, follow in seen)
    assert "x-api-key" in seen[1][1] and "x-goog-api-key" in seen[2][1]


def test_rejected_key_is_422_and_outage_is_503(monkeypatch):
    monkeypatch.setattr(gateway.httpx, "get", lambda url, **kw: reply(401, {}))
    with pytest.raises(HTTPException) as rejected:
        gateway.other_provider_models("openai", "bad")
    assert rejected.value.status_code == 422

    def down(url, **kw):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(gateway.httpx, "get", down)
    with pytest.raises(HTTPException) as outage:
        gateway.other_provider_models("openai", "k")
    assert outage.value.status_code == 503


def test_custom_provider_with_private_or_missing_base_url_is_refused_before_any_request(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("no request may be sent")
    monkeypatch.setattr(gateway.httpx, "get", forbidden)
    monkeypatch.setattr(gateway.httpx, "post", forbidden)
    for base in (None, "https://10.0.0.1/v1", "http://api.example.com/v1", "https://169.254.169.254/"):
        with pytest.raises(HTTPException) as refused:
            gateway.other_provider_models("custom", "k", base)
        assert refused.value.status_code == 422
        with pytest.raises(HTTPException):
            gateway.other_provider_reply("custom", "k", "m", "s", "u", base)


def test_reply_is_parsed_per_provider(monkeypatch):
    monkeypatch.setattr(gateway.httpx, "post", lambda url, **kw: reply(200, {"content": [{"type": "text", "text": "{}"}], "usage": {"input_tokens": 1}}, "POST"))
    text, usage = gateway.other_provider_reply("anthropic", "k", "claude-x", "s", "u")
    assert text == "{}" and usage == {"input_tokens": 1}
