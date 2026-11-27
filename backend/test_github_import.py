"""Read-only GitHub App intake tests using a simulated upstream provider."""
import io
import json
import logging
from zipfile import ZipFile

import httpx
from joserfc import jwt
from joserfc.jwk import RSAKey
import pytest

from . import github_import as intake, platform_jobs as jobs, platform_runtime as store
from .test_platform_runtime import platform  # noqa: F401


COMMIT = "a" * 40
PROVIDER_TOKEN = "integration-test-token"


def files():
    raw = io.BytesIO()
    with ZipFile(raw, "w") as archive:
        archive.writestr("Octo-Example-aaaaaaa/index.html", "<p>Private project</p>")
    return raw.getvalue()


@pytest.fixture
def github(platform, tmp_path, monkeypatch):
    _owner, _other, ctx = platform
    rsa = RSAKey.generate_key()
    secret = tmp_path / "github.key"
    secret.write_bytes(rsa.as_pem(private=True))
    monkeypatch.setenv("BASIRA_GITHUB_APP_ID", "441")
    monkeypatch.setenv("BASIRA_GITHUB_APP_KEY_FILE", str(secret))
    monkeypatch.setenv("BASIRA_GITHUB_INSTALLATIONS", json.dumps({ctx.org_id: [22]}))
    recorded = []
    feature = {
        "visible": True,
        "redirect": f"https://codeload.github.com/Octo/Example/legacy.zip/{COMMIT}?token=signed-location",
        "archive": files(),
    }

    def route(request):
        recorded.append(request)
        path = request.url.path
        if path == "/app/installations/22/access_tokens":
            token = request.headers["authorization"].split(" ", 1)[1]
            claims = jwt.decode(token, rsa, algorithms=["RS256"]).claims
            assert claims["iss"] == "441" and claims["exp"] - claims["iat"] <= 600
            assert request.headers["x-github-api-version"] == intake.API_VERSION
            body = json.loads(request.content)
            assert body.pop("permissions") == {"contents": "read"}
            assert body in ({"repositories": ["example"]}, {"repository_ids": [11]})
            return httpx.Response(201, json={"token": PROVIDER_TOKEN, "permissions": {"contents": "read"}})
        if request.url.host == "codeload.github.com":
            assert not request.headers.get("authorization")
            return httpx.Response(200, stream=httpx.ByteStream(feature["archive"]))
        assert request.url.host == "api.github.com"
        assert request.headers["authorization"] == f"Bearer {PROVIDER_TOKEN}"
        if path == "/installation/repositories":
            repos = [{"full_name": "Octo/Example", "id": 11}] if feature["visible"] else []
            return httpx.Response(200, json={"repositories": repos})
        if path == "/installation/token":
            assert request.method == "DELETE"
            return httpx.Response(204)
        if path == f"/repos/Octo/Example/commits/{COMMIT}":
            return httpx.Response(200, json={"sha": COMMIT})
        if path == f"/repos/Octo/Example/zipball/{COMMIT}":
            logging.getLogger("httpcore.http11").debug("receive_response_headers.complete %s", feature["redirect"])
            return httpx.Response(302, headers={"Location": feature["redirect"]})
        raise AssertionError(f"Unexpected provider request: {request.method} {path}")

    monkeypatch.setattr(intake, "client", lambda: httpx.Client(transport=httpx.MockTransport(route)))
    return recorded, feature


def source_paths(ctx):
    return (f"/api/platform/organizations/{ctx.org_id}/github-source",
            f"/api/platform/projects/{ctx.project_id}/github-source")


def link(owner, org_path, ctx, **changes):
    return owner.put(org_path, json={"project_id": ctx.project_id, "repository": "octo/example",
                                     "installation_id": 22, **changes})


def enqueue(owner, project_path, key="github-fixture", **changes):
    return owner.post(project_path + "/scans", headers={"Idempotency-Key": key}, json={
        "commit": COMMIT, "scope_version": 0, "acknowledge_scope": True, **changes,
    })


def test_import_is_pinned_idempotent_project_scoped_and_revocable(platform, github, caplog):
    owner, outsider, ctx = platform
    recorded, _features = github
    org, project = source_paths(ctx)
    assert outsider.get(org).status_code == 404
    assert outsider.get(project).status_code == 404
    assert not owner.get(project).json()["available"]
    assert link(owner, org, ctx, installation_id=23).status_code == 409
    assert not recorded
    configured = link(owner, org, ctx)
    assert configured.status_code == 200, configured.text
    assert owner.get(org).json()["installation_ids"] == [22]
    assert "installation_id" not in owner.get(project).json()["connection"]
    assert enqueue(owner, project, commit="main").status_code == 422
    with caplog.at_level(logging.DEBUG):
        created = enqueue(owner, project)
        logging.getLogger("httpx").info("Unrelated HTTPX request metadata")
    assert created.status_code == 202, created.text
    assert "signed-location" not in caplog.text and PROVIDER_TOKEN not in caplog.text
    assert "Unrelated HTTPX request metadata" in caplog.text
    identifier = created.json()["id"]
    locator = {"connection_id": configured.json()["id"], "commit": COMMIT, "repository": "Octo/Example"}
    assert created.json()["artifact"]["github"] == locator
    upstream_requests = len(recorded)
    assert enqueue(owner, project).json()["id"] == identifier
    assert len(recorded) == upstream_requests

    jobs.execute_scan(ctx.org_id, ctx.project_id, identifier)
    prefix = f"/api/platform/projects/{ctx.project_id}"
    provenance = owner.get(f"{prefix}/scans/{identifier}/provenance")
    assert provenance.json()["snapshot"]["github"] == locator
    assert owner.get(f"{prefix}/reports/{identifier}").status_code == 200
    assert outsider.get(f"{prefix}/scans/{identifier}/provenance").status_code == 404
    assert all(PROVIDER_TOKEN not in response.text for response in (configured, created, provenance))
    assert owner.delete(org, params={"project_id": ctx.project_id}).status_code == 204
    assert enqueue(owner, project, key="after-revoke").status_code == 409
    assert len(recorded) == upstream_requests


def test_untrusted_redirect_oversize_or_removed_repository_is_rejected(platform, github):
    owner, _other, ctx = platform
    recorded, features = github
    org, project = source_paths(ctx)
    assert link(owner, org, ctx).status_code == 200
    features["visible"] = False
    assert enqueue(owner, project, key="removed-repo").status_code == 409
    features["visible"] = True
    original = features["redirect"]
    features["redirect"] = f"https://redirect.invalid/Octo/Example/legacy.zip/{COMMIT}"
    assert enqueue(owner, project, key="external-redirect").status_code == 502
    assert not any(item.url.host == "redirect.invalid" for item in recorded)
    features["redirect"] = original
    features["archive"] = b"PK\x03\x04" + b"x" * intake.MAX_ARTIFACT
    assert enqueue(owner, project, key="large-archive").status_code == 413
    assert owner.get(f"/api/platform/projects/{ctx.project_id}/scans").json()["scans"] == []


def test_revocation_during_download_blocks_enqueue(platform, github, monkeypatch):
    owner, _other, ctx = platform
    org, project = source_paths(ctx)
    assert link(owner, org, ctx).status_code == 200

    def revoke_and_return(row, commit):
        assert owner.delete(org, params={"project_id": ctx.project_id}).status_code == 204
        return files()

    monkeypatch.setattr(intake, "snapshot", revoke_and_return)
    assert enqueue(owner, project, key="race-with-revocation").status_code == 409
    assert owner.get(f"/api/platform/projects/{ctx.project_id}/scans").json()["scans"] == []
