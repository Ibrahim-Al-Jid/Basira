import pytest

from .llm_providers import (CUSTOM, PROVIDERS, custom_base, chat_request, cost_warning, mask_key, models_request, parse_chat, parse_models,
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


def public(*addresses):
    return lambda host, port, type=None: [(0, 0, 0, "", (address, port)) for address in addresses]


def test_custom_provider_accepts_a_public_https_base_and_builds_openai_style_requests():
    base = custom_base("https://API.Example.com/v1/", public("93.184.216.34"))
    assert base == "https://api.example.com/v1"
    assert [item["id"] for item in public_providers() if item["custom"]] == [CUSTOM]
    rows = parse_models(CUSTOM, {"data": [{"id": "my-model"}]})
    assert rows[0]["cost"] == "unknown" and cost_warning(CUSTOM, rows[0])


@pytest.mark.parametrize("url", [
    "http://api.example.com/v1", "https://user:pw@api.example.com/v1", "https://api.example.com:8443/v1",
    "https://localhost/v1", "https://db.internal/v1", "https://127.0.0.1/v1", "https://10.0.0.5/v1",
    "https://169.254.169.254/latest", "https://[::1]/v1", "https://api.example.com/v1?x=1", "", "ftp://x.com"])
def test_custom_provider_rejects_unsafe_base_urls(url):
    with pytest.raises(ValueError):
        custom_base(url, public("93.184.216.34"))


def test_custom_provider_rejects_names_that_resolve_to_private_addresses_even_when_mixed():
    with pytest.raises(ValueError):
        custom_base("https://api.example.com/v1", public("93.184.216.34", "10.1.2.3"))


REQUEST = {"method": "GET", "url": "https://api.example.com/v1/models", "headers": {"Authorization": "Bearer k"}}


def test_pin_request_resolves_again_and_connects_to_a_public_address_keeping_the_host_name():
    from .llm_providers import pin_request
    request = REQUEST
    pinned = pin_request(request, public("93.184.216.34"))
    assert pinned["url"] == "https://93.184.216.34/v1/models"
    assert pinned["headers"]["Host"] == "api.example.com" and pinned["extensions"] == {"sni_hostname": "api.example.com"}
    assert pinned["headers"]["Authorization"] == "Bearer k"
    v6 = pin_request(request, public("2606:2800:220:1:248:1893:25c8:1946"))
    assert v6["url"].startswith("https://[2606:2800:220:1:248:1893:25c8:1946]/")


def test_dns_rebinding_after_validation_is_refused_at_connect_time():
    from .llm_providers import pin_request
    request = REQUEST
    for answers in (("10.0.0.5",), ("93.184.216.34", "169.254.169.254"), ("127.0.0.1",), ()):
        with pytest.raises(ValueError, match="public|resolve"):
            pin_request(request, public(*answers))

    def fail(*args, **kwargs):
        raise OSError("no such host")
    with pytest.raises(ValueError, match="resolve"):
        pin_request(request, fail)
    literal = {**REQUEST, "url": "https://93.184.216.34/v1/models"}
    assert pin_request(literal, fail) == literal
