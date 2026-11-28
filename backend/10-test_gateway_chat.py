"""The Hunter's /chat route: the key stays in the gateway and every turn takes one call out of a per-scan cap."""
import httpx
import sqlalchemy as sa

from . import model_gateway, platform_runtime as store
from .platform_db import platform_session
from .test_platform_runtime import platform  # noqa: F401  (fixture)
from .test_model_connections import (  # noqa: F401  (fixture and helpers)
    IDENTIFIER, KEY, MODEL, credential_platform, project_root, reply, setup_key, _reserve,
)

HEADERS = {"Authorization": "Bearer test-only-gateway-auth"}
MESSAGES = [{"role": "system", "content": "You are the Hunter."}, {"role": "user", "content": "Project map: {}"}]


def prepare(client, ctx, label, monkeypatch, sent):
    assert setup_key(client, ctx).status_code == 200
    policy = {"allowed_kinds": ["html"], "model_connection": IDENTIFIER}
    assert client.put(project_root(ctx) + "/policy", json=policy).status_code == 200
    facts = _reserve(client, ctx, label)
    facts.pop("counts")

    def post(url, *, headers, timeout, trust_env, json):
        sent.append((url, headers["Authorization"].split(" ", 1)[1], json))
        return reply(url, {"choices": [{"message": {"content": '{"candidates":[]}'}}],
                           "usage": {"prompt_tokens": 12, "completion_tokens": 4}}, method="POST")
    monkeypatch.setattr(httpx, "post", post)
    return {**facts, "messages": MESSAGES}


def calls_made(ctx, scan):
    with platform_session() as db:
        return db.scalar(sa.select(store.scans.c.agent_calls).where(store.scans.c.id == scan))


def test_chat_returns_text_and_usage_and_sends_the_key_only_to_the_provider(credential_platform, monkeypatch):
    client, _, gateway, ctx, _, _ = credential_platform
    sent = []
    body = prepare(client, ctx, "chat-ok-reserve", monkeypatch, sent)
    answer = gateway.post("/chat", json=body, headers=HEADERS)
    assert answer.status_code == 200 and answer.json() == {"content": '{"candidates":[]}', "usage": {"input": 12, "output": 4}}
    assert KEY not in answer.text
    [(url, key, payload)] = sent
    assert url == model_gateway.PROVIDER_URL + "/chat/completions" and key == KEY
    assert payload["model"] == MODEL and payload["provider"]["allow_fallbacks"] is False
    assert [item["role"] for item in payload["messages"]] == ["system", "user"]


def test_chat_stops_at_the_per_scan_cap_and_the_advisor_slot_is_then_gone(credential_platform, monkeypatch):
    client, _, gateway, ctx, _, _ = credential_platform
    sent = []
    body = prepare(client, ctx, "chat-cap", monkeypatch, sent)
    for _turn in range(model_gateway.CHAT_CALL_CAP):
        assert gateway.post("/chat", json=body, headers=HEADERS).status_code == 200
    assert gateway.post("/chat", json=body, headers=HEADERS).status_code == 409
    assert len(sent) == model_gateway.CHAT_CALL_CAP and calls_made(ctx, body["scan_id"]) == model_gateway.CHAT_CALL_CAP
    advisor = {**body, "counts": {"http-script": 1}}
    advisor.pop("messages")
    assert gateway.post("/priority", json=advisor, headers=HEADERS).status_code == 409


def test_chat_refuses_bad_shapes_without_spending_a_call(credential_platform, monkeypatch):
    client, _, gateway, ctx, _, _ = credential_platform
    sent = []
    body = prepare(client, ctx, "chat-shape", monkeypatch, sent)
    bad = [
        {**body, "messages": MESSAGES[1:] + MESSAGES[:1]},
        {**body, "messages": MESSAGES + [{"role": "system", "content": "x"}]},
        {**body, "messages": MESSAGES[:1]},
        {**body, "messages": [{"role": "tool", "content": "x"}] + MESSAGES},
        {**body, "messages": [MESSAGES[0], {"role": "user", "content": "x" * (model_gateway.CHAT_CONTENT_LIMIT + 1)}]},
        {**body, "messages": MESSAGES * 30},
        {**body, "api_key": KEY},
    ]
    for item in bad:
        assert gateway.post("/chat", json=item, headers=HEADERS).status_code == 422
    assert sent == [] and calls_made(ctx, body["scan_id"]) == 0


def test_chat_needs_the_service_token_a_live_lease_and_the_pinned_model(credential_platform, monkeypatch):
    client, _, gateway, ctx, _, _ = credential_platform
    sent = []
    body = prepare(client, ctx, "chat-auth", monkeypatch, sent)
    assert gateway.post("/chat", json=body).status_code in (401, 403)
    assert gateway.post("/chat", json=body, headers={"Authorization": "Bearer wrong"}).status_code in (401, 403)
    assert gateway.post("/chat", json={**body, "lease": "f" * 32}, headers=HEADERS).status_code == 409
    assert gateway.post("/chat", json={**body, "model": MODEL + "-other"}, headers=HEADERS).status_code == 409
    assert gateway.post("/chat", json={**body, "scan_id": "a" * 32}, headers=HEADERS).status_code == 409
    assert sent == [] and calls_made(ctx, body["scan_id"]) == 0


def test_other_providers_get_one_system_text_and_the_rest_folded_into_one_user_text(credential_platform, monkeypatch):
    client, _, gateway, ctx, _, _ = credential_platform
    body = prepare(client, ctx, "chat-other", monkeypatch, [])
    seen = []

    def fake(provider, key, model, system, user, base_url=None):
        seen.append((provider, system, user))
        return "final", {"input_tokens": 3}

    monkeypatch.setattr(model_gateway, "other_provider_reply", fake)
    turns = MESSAGES + [{"role": "assistant", "content": "ok"}, {"role": "user", "content": "<data>x</data>"}]
    answer = gateway.post("/chat", json={**body, "provider": "openai", "messages": turns}, headers=HEADERS)
    assert answer.status_code == 200 and answer.json()["content"] == "final" and answer.json()["usage"]["input"] == 3
    assert seen == [("openai", "You are the Hunter.", "[user]\nProject map: {}\n\n[assistant]\nok\n\n[user]\n<data>x</data>")]


def test_provider_failure_is_a_502_and_malformed_usage_is_estimated(credential_platform, monkeypatch):
    client, _, gateway, ctx, _, _ = credential_platform
    body = prepare(client, ctx, "chat-fail", monkeypatch, [])
    monkeypatch.setattr(httpx, "post", lambda url, **kw: reply(url, {"choices": [{"message": {"content": None}}]}, method="POST"))
    assert gateway.post("/chat", json=body, headers=HEADERS).status_code == 502
    monkeypatch.setattr(httpx, "post", lambda url, **kw: reply(
        url, {"choices": [{"message": {"content": "abcd" * 10}}], "usage": {"prompt_tokens": -5, "completion_tokens": "x"}},
        method="POST"))
    usage = gateway.post("/chat", json=body, headers=HEADERS).json()["usage"]
    assert usage["input"] > 0 and usage["output"] == 11
