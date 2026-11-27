"""Exercise the one-call gateway contract with synthetic provider responses."""

from copy import deepcopy
from json import dumps, loads

import httpx
import pytest
from fastapi.testclient import TestClient

from . import model_gateway as gateway
from .source_adapters import SOURCE_TOOLS


IDS = dict(org_id="a" * 32, project_id="b" * 32, scan_id="c" * 32, lease="d" * 32)
CONNECTION = {"model": "fixture/advisor", "generation": "operator"}
GATEWAY_URL = "http://fixture-gateway.invalid"
SOURCE_RULE = SOURCE_TOOLS[0].rule
SOURCE_PRIVATE = "private-file-and-untrusted-content"
ADVICE = {
    "priority": [SOURCE_RULE, "http-script"],
    "planning": [{"tool": "gitleaks", "label": "review_tool_findings"}],
    "validation": [{"evidence": "e1", "label": "review_evidence"}],
    "explanation": [{"evidence": "e2", "label": "read_remediation"}],
}


def artifact_report():
    return {
        "execution": {"input_kind": "repository", "source_sha256": "a" * 64, "trace_id": "b" * 32},
        "tool_selection": [{"id": "gitleaks", "status": "selected"},
                           {"id": "semgrep", "status": "skipped"},
                           {"id": "unapproved-upload-tool", "status": "selected"}],
        "findings": [
            {"fingerprint": "1" * 64, "rule": "http-script", "severity": "medium",
             "assessment": "observed", "path": SOURCE_PRIVATE + ".html", "line": 1},
            {"fingerprint": "2" * 64, "rule": SOURCE_RULE, "severity": "high",
             "assessment": "review_required", "evidence": SOURCE_PRIVATE, "line": 2},
        ],
        "metrics": {"modelCalls": 0},
        "coverage": [{"rule": SOURCE_RULE, "status": "matched"}],
        "input_paths": [SOURCE_PRIVATE + ".html"],
    }


@pytest.fixture
def mocked_gateway(monkeypatch):
    monkeypatch.setenv("MARSAD_GATEWAY_TOKEN", "fixture-service-token")
    monkeypatch.setattr(gateway, "gateway_config", lambda: (
        GATEWAY_URL, {"Authorization": "Bearer fixture-service-token"},
    ))
    monkeypatch.setattr(gateway, "operator_enabled", lambda _org: CONNECTION["model"])
    monkeypatch.setattr(gateway, "start_model_call", lambda _body: (None,))
    monkeypatch.setattr(gateway, "openrouter_secret", lambda: "fixture-provider-token")
    with TestClient(gateway.app) as client:
        yield client


def enrich_with(monkeypatch, client, answer, report):
    calls = []

    def intercept(url, *, json: dict, headers, timeout, trust_env):
        assert not trust_env
        if url == GATEWAY_URL + "/priority":
            response = client.post("/priority", headers=headers, json=json)
            return httpx.Response(response.status_code, request=httpx.Request("POST", url),
                                  content=response.content)
        assert url == gateway.PROVIDER_URL + "/chat/completions"
        assert timeout == 12
        calls.append(json)
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "choices": [{"message": {"content": dumps(answer)}}],
            "usage": {"prompt_tokens": 37, "completion_tokens": 22},
        })

    monkeypatch.setattr(gateway.httpx, "post", intercept)
    gateway.enrich(report, CONNECTION, **IDS, execution_advice=True)
    return calls


def test_advisor_sends_only_allowlisted_facts_and_preserves_evidence(monkeypatch, mocked_gateway):
    report = artifact_report()
    original = deepcopy(report)
    [request] = enrich_with(monkeypatch, mocked_gateway, ADVICE, report)
    assert request.keys() == {"model", "max_tokens", "provider", "messages"}
    assert request["max_tokens"] == 1200
    assert request["provider"] == {"data_collection": "deny", "allow_fallbacks": False}
    content = request["messages"][-1]["content"]
    assert loads(content) == {
        "counts": {"http-script": 1, SOURCE_RULE: 1},
        "input_kind": "repository",
        "tools": ["gitleaks"],
        "evidence": [
            {"id": "e1", "rule": "http-script", "severity": "medium", "assessment": "observed"},
            {"id": "e2", "rule": SOURCE_RULE, "severity": "high", "assessment": "review_required"},
        ],
    }
    for forbidden in (SOURCE_PRIVATE, *IDS.values(), "a" * 64, "1" * 64, "2" * 64):
        assert forbidden not in content
    assert {field: report[field] for field in ("findings", "coverage", "execution", "input_paths")} == {
        field: original[field] for field in ("findings", "coverage", "execution", "input_paths")
    }
    assert report["agent_advisory"] == {
        "version": "marsad-advisor-1",
        "planning": ADVICE["planning"],
        "validation": [{"fingerprint": "1" * 64, "label": "review_evidence"}],
        "explanation": [{"fingerprint": "2" * 64, "label": "read_remediation"}],
    }
    assert report["priority"] == ADVICE["priority"]
    assert report["metrics"] == {"modelCalls": 1, "inputTokens": 37, "outputTokens": 22}


@pytest.mark.parametrize("untrusted", [
    {"planning": [{"tool": "semgrep", "label": "review_tool_coverage"}]},
    {"validation": [{"evidence": "e3", "label": "review_evidence"}]},
    {"validation": [{"evidence": "e1", "label": "review_evidence"}] * 2},
    {"explanation": [{"evidence": "e1", "label": "invented-description"}]},
    {"priority": [SOURCE_RULE, SOURCE_RULE]},
    {"instructions": "untrusted content"},
])
def test_rejects_entire_invalid_suggestion_bundle(monkeypatch, mocked_gateway, untrusted):
    report = artifact_report()
    assert len(enrich_with(monkeypatch, mocked_gateway, {**ADVICE, **untrusted}, report)) == 1
    assert report == {**artifact_report(), "enrichment": "fallback", "metrics": {"modelCalls": 1}}


def test_rejects_unregistered_facts_before_taking_budget(monkeypatch, mocked_gateway):
    monkeypatch.setattr(gateway, "start_model_call", lambda _body: pytest.fail("Call slot was consumed"))
    reply = mocked_gateway.post("/priority", headers={"Authorization": "Bearer fixture-service-token"}, json={
        **IDS, **CONNECTION, "counts": {"http-script": 1}, "connection": gateway.CONNECTION_ID,
        "advisor": {
            "input_kind": "repository", "tools": ["semgrep"],
            "evidence": [{"id": "e1", "rule": "http-script", "severity": "low", "assessment": "observed"}],
        },
    })
    assert reply.status_code == 422


def test_transport_failure_keeps_deterministic_report(monkeypatch, mocked_gateway):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("unavailable")

    monkeypatch.setattr(gateway.httpx, "post", fail)
    report = artifact_report()
    gateway.enrich(report, CONNECTION, **IDS, execution_advice=True)
    assert report == {**artifact_report(), "enrichment": "fallback", "metrics": {"modelCalls": None}}
