import base64
import io
import json
import socket
from zipfile import ZipFile

import pytest

from .artifact_review import RULESET_VERSION
from .offline_worker import scan_payload
from .scan_contracts import analyzer_plan


def scan(kind, name, raw, *, policy=None):
    return scan_payload({
        "kind": kind, "name": name, "content": base64.b64encode(raw).decode("ascii"),
        "policy": {"_analysis_plan": analyzer_plan(kind), "_ruleset_version": RULESET_VERSION, **(policy or {})},
    })


def saved_zap():
    return {"@version": "2.16.1", "site": [{
        "@name": "https://example.test:443", "@host": "example.test", "@ssl": "true",
        "alerts": [
            {"pluginid": "10021", "alertRef": "10021", "alert": "private alert description",
             "riskcode": "3", "instances": [
                 {"uri": "https://example.test/private-page?session=secret-value", "method": "GET",
                  "request-header": "Authorization: secret-value", "response-body": "private page content"},
             ]},
            {"pluginid": "40012", "alertRef": "40012", "instances": [
                {"uri": "https://example.test/ignored", "attack": "private alert data"},
            ]},
        ],
    }]}


def deny_network(*_args, **_kwargs):
    pytest.fail("Offline document scanner attempted network access")


def test_zap_import_provenance_scope_and_minimal_projection(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)
    report = scan("zap", "saved-zap.json", json.dumps(saved_zap()).encode(),
                  policy={"base_url": "https://example.test"})["result"]
    assert report["metrics"]["checksRun"] == 0
    assert report["status"] == "completed"
    assert report["imported_evidence"] == {
        "source": "zap-passive-report", "status": "imported", "accepted_alerts": 1, "skipped_alerts": 1,
    }
    item, = report["findings"]
    assert (item["rule"], item["severity"], item["assessment"]) == ("ZAP-10021", "low", "review_required")
    assert item["origins"][0]["tool"] == "zap-passive-report"
    assert item["path"] == "saved-zap.json"
    coverage = {row["rule"]: row for row in report["coverage"]}
    assert coverage["ZAP-10035"]["reason"] == "alert_not_present_in_export"
    assert coverage["ZAP-10035"]["status"] == "not_applicable"
    assert coverage["ZAP-10021"]["status"] == "matched"
    serialized = json.dumps(report)
    for secret in ("private-page", "private page content", "secret-value", "private alert description", "40012"):
        assert secret not in serialized


@pytest.mark.parametrize("target,instance", [
    (None, "https://example.test/home"),
    ("http://example.test", "https://example.test/home"),
    ("https://example.test", "https://different.test/home"),
    ("https://example.test", "https://user:pass@example.test/home"),
    ("https://example.test", "https://example.test:0/home"),
])
def test_zap_rejects_target_mismatch(target, instance):
    document = saved_zap()
    document["site"][0]["alerts"][0]["instances"][0]["uri"] = instance
    result = scan("zap", "saved-zap.json", json.dumps(document).encode(), policy={"base_url": target})
    assert "أصل الموقع" in result["error"]


def test_repository_lists_css_and_skipped_files():
    source = io.BytesIO()
    with ZipFile(source, "w") as archive:
        archive.writestr("project/index.html", '<link rel="stylesheet" href="./style.css">')
        archive.writestr("project/style.css", ".card:hover { color: #444; }")
        archive.writestr("project/card.png", b"\x89PNG\x00")
    report = scan("repository", "rollup.zip", source.getvalue())["result"]
    assert report["input_paths"] == ["project/index.html", "project/style.css"]
    assert report["input_manifest"] == [
        {"path": "project/card.png", "status": "skipped", "reason": "unsupported_extension"},
        {"path": "project/index.html", "status": "included", "reason": None},
        {"path": "project/style.css", "status": "included", "reason": None},
    ]


def openapi():
    return {
        "openapi": "3.1.1", "info": {"title": "Sample", "version": "1"},
        "paths": {"/home": {"get": {"security": [
            {"oauth": ["read"]}, {"unavailable": []}, {"undefined": []}, {},
        ]}}},
        "components": {"securitySchemes": {
            "oauth": {"type": "oauth2", "flows": {"clientCredentials": {
                "tokenUrl": "https://example.test/private-token", "scopes": {"read": "Private scope label"},
            }}},
            "localAlias": {"$ref": "#/components/securitySchemes/oauth"},
            "unavailable": {"$ref": "https://example.test/private-schema.json"},
        }},
    }


def test_openapi_auth_inventory_does_not_fetch_references(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    report = scan("openapi", "contract.json", json.dumps(openapi()).encode())["result"]
    inventory = report["api_inventory"]
    assert inventory["security_schemes"] == {"oauth2": 2, "unresolved": 1}
    assert inventory["unresolved_security_requirements"] == 2
    assert inventory["anonymous_operations"] == 1
    assert "private-token" not in json.dumps(report)
    assert "Private scope label" not in json.dumps(report)


@pytest.mark.parametrize("mutate", [
    lambda doc: doc.update(openapi="2.0"),
    lambda doc: doc.update(components={"securitySchemes": []}),
    lambda doc: doc.update(components={"securitySchemes": {"bad": {"type": "other"}}}),
    lambda doc: doc["paths"]["/home"]["get"].update(security=[{"oauth": 1}]),
])
def test_openapi_rejects_invalid_contract(mutate):
    document = openapi()
    mutate(document)
    result = scan("openapi", "contract.json", json.dumps(document).encode())
    assert "OpenAPI" in result["error"]


def test_openapi_rejects_duplicate_security_definitions():
    result = scan("openapi", "contract.json", b'{"openapi":"3.1.0","security":[],"security":[{}]}')
    assert "error" in result


def test_unique_observations_keeps_same_line_instances_but_merges_tools():
    from backend.artifact_review import unique_observations

    def hit(tool):
        return {"rule": "http-script", "path": "a.html", "line": 1, "evidence": "x",
                "origins": [{"tool": tool, "rule": "http-script"}]}

    assert len(unique_observations([hit("html"), hit("html")])) == 2
    merged = unique_observations([hit("html"), hit("other")])
    assert len(merged) == 1 and len(merged[0]["origins"]) == 2
