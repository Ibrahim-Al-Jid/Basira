import base64
import io
import json
from zipfile import ZipFile

from . import platform_jobs as jobs
from .test_platform_runtime import platform, submit  # noqa: F401


def artifact(kind, name, raw, **fields):
    return {"kind": kind, "name": name, "content": base64.b64encode(raw).decode(),
            "scope_version": 0, "acknowledge_scope": True, **fields}


def finish(owner, scope, body, key):
    response = submit(owner, scope, body, key=key)
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    jobs.execute_scan(scope.org_id, scope.project_id, identifier)
    path = f"/api/platform/projects/{scope.project_id}"
    return owner.get(f"{path}/reports/{identifier}"), owner.get(f"{path}/scans/{identifier}/provenance")


def test_repository_defaults_and_explicit_policy_still_wins(platform):
    owner, _, scope = platform
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("site/index.html", '<form action="http://example.test"></form>')
        archive.writestr("site/Dockerfile", "FROM python:3\nUSER 0\n")
    body = artifact("repository", "project.zip", stream.getvalue())
    report, trace = finish(owner, scope, body, "repository-default")
    assert report.is_success
    assert {row["path"] for row in report.json()["findings"]} == {"site/index.html", "site/Dockerfile"}
    assert trace.json()["snapshot"]["kind"] == "repository"
    assert owner.put(f"/api/platform/projects/{scope.project_id}/policy",
                     json={"allowed_kinds": ["html"]}).is_success
    assert submit(owner, scope, {**body, "scope_version": 1}, key="repository-restricted").status_code == 409


def test_openapi_contract_inventory_reference_and_exports(platform):
    owner, other, scope = platform
    document = {
        "openapi": "3.1.1", "info": {"title": "Example", "version": "1"},
        "servers": [{"url": "http://internal.example.test"}],
        "security": [{"service": []}],
        "paths": {
            "/status": {"get": {"security": [{}]}},
            "/orders": {"get": {"requestBody": {"$ref": "#/components/requestBodies/Contract"}}},
        },
        "components": {"requestBodies": {"Contract": {"schema": {"$ref": "https://private.example.test/ref.json"}}}},
    }
    body = artifact("openapi", "api.json", json.dumps(document).encode(),
                    target_reference="https://evidence.example.test/ignored")
    report, trace = finish(owner, scope, body, "openapi-contract")
    assert report.is_success, report.text
    assert report.json()["api_inventory"] == {
        "version": "3.1.1", "operations": 2, "declared_auth": 1, "anonymous_operations": 1,
        "local_references": 1, "unresolved_references": 1,
        "security_schemes": {}, "unresolved_security_requirements": 1,
    }
    assert {row["rule"] for row in report.json()["findings"]} == {"API-01", "API-02", "API-03"}
    assert "private.example.test" not in report.text and "internal.example.test" not in report.text
    assert trace.json()["asset"]["reference"] == "https://evidence.example.test"
    assert trace.json()["asset"]["source"] == "scan_reference"
    path = report.request.url.path
    assert other.get(path).status_code == 404
    assert owner.get(path + "/download?format=pdf").content.startswith(b"%PDF")
    assert submit(owner, scope, {**body, "target_reference": "https://user:secret@host.test"}, key="invalid-url").status_code == 422
    assert owner.put(f"/api/platform/projects/{scope.project_id}/policy",
                     json={"allowed_kinds": ["openapi"], "base_url": "https://policy.example.test"}).is_success
    assert submit(owner, scope, {**body, "scope_version": 1}, key="wrong-origin").status_code == 409
