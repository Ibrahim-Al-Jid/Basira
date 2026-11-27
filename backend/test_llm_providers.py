import pytest

from .llm_providers import (PROVIDERS, chat_request, cost_warning, mask_key, models_request, parse_chat, parse_models,
                            public_providers)


def test_four_providers_and_only_openrouter_has_a_free_path():
    assert set(PROVIDERS) == {"openrouter", "openai", "anthropic", "google"}
    assert [item["id"] for item in public_providers() if item["free_path"]] == ["openrouter"]


@pytest.mark.parametrize("provider,header", [("openrouter", "Authorization"), ("openai", "Authorization"),
                                             ("anthropic", "x-api-key"), ("google", "x-goog-api-key")])
def test_auth_goes_in_headers_never_in_the_url(provider, header):
    for request in (models_request(provider, "k-secret"), chat_request(provider, "k-secret", "m", "s", "u")):
        assert header in request["headers"] and "k-secret" not in request["url"]


def test_openrouter_free_models_sort_first_and_paid_requires_warning():
    rows = parse_models("openrouter", {"data": [
        {"id": "a/paid", "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
        {"id": "z/free:free", "pricing": {"prompt": "0", "completion": "0"}}]})
    assert [row["id"] for row in rows] == ["z/free:free", "a/paid"]
    assert cost_warning("openrouter", rows[0]) is None and "paid model" in cost_warning("openrouter", rows[1])


def test_other_providers_parse_and_never_claim_free():
    openai = parse_models("openai", {"data": [{"id": "gpt-x"}]})
    anthropic = parse_models("anthropic", {"data": [{"id": "claude-x", "display_name": "Claude X"}]})
    google = parse_models("google", {"models": [{"name": "models/gemini-x", "supportedGenerationMethods": ["generateContent"]},
                                                {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]}]})
    assert openai[0]["cost"] == anthropic[0]["cost"] == "paid" and anthropic[0]["name"] == "Claude X"
    assert [row["id"] for row in google] == ["gemini-x"] and google[0]["cost"] == "unknown"
    assert cost_warning("google", google[0])


def test_chat_shapes_round_trip_and_bad_payloads_are_empty():
    assert parse_chat("openai", {"choices": [{"message": {"content": "hi"}}]}) == "hi"
    assert parse_chat("anthropic", {"content": [{"type": "text", "text": "hi"}]}) == "hi"
    assert parse_chat("google", {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}) == "hi"
    assert all(parse_chat(name, {"oops": 1}) == "" for name in PROVIDERS)
    assert parse_models("openai", "nope") == [] and chat_request("google", "k", "g", "s", "u")["url"].endswith("/models/g:generateContent")


def test_unknown_provider_is_rejected_and_keys_are_masked():
    with pytest.raises(ValueError):
        models_request("evil", "k")
    assert mask_key("sk-abcdefghijkl") == "********ijkl" and mask_key("") == "" and "abc" not in mask_key("abc")
