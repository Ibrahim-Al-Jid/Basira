"""Model credential and gateway acceptance using synthetic OpenRouter responses."""
from base64 import urlsafe_b64encode

from fastapi.testclient import TestClient
import httpx
import pytest
import sqlalchemy as sa

from . import main, model_connections as connections, model_gateway, platform_runtime as store
from .identity import SESSION_COOKIE
from .platform_db import Membership, platform_session, utc_now
from .test_platform_runtime import artifact, platform, submit  # noqa: F401

HOST = "http://127.0.0.1"
ORIGIN = {"Origin": HOST}
GATEWAY = "http://model-gateway.test"
MODEL = "testing/defensive"
KEY = "test-openrouter-secret-alpha"
ROTATED = "test-openrouter-secret-beta"
INVALID = "test-openrouter-invalid-key"
IDENTIFIER = connections.CONNECTION_ID


def reply(url, data, status=200, method="GET"):
    return httpx.Response(status, request=httpx.Request(method, url), json=data)


@pytest.fixture
def credential_platform(platform, monkeypatch, tmp_path):
    owner, outsider, ctx = platform
    master = tmp_path / "provider-encryption.key"
    master.write_bytes(urlsafe_b64encode(bytes(range(32))))
    monkeypatch.setenv("BASIRA_MODEL_MASTER_KEY_FILE", str(master))
    monkeypatch.setenv("BASIRA_GATEWAY_URL", GATEWAY)
    monkeypatch.setenv("BASIRA_GATEWAY_TOKEN", "test-only-gateway-auth")
    calls = []
    with TestClient(model_gateway.app) as gateway:
        def get(url, *, headers, timeout, trust_env):
            assert not trust_env and timeout <= 6
            if url == GATEWAY + "/managed-health":
                response = gateway.get("/managed-health", headers=headers)
                return reply(url, response.json(), status=response.status_code)
            key = headers["Authorization"].split(" ", 1)[1]
            calls.append(("verify", url, key))
            if key == INVALID:
                return reply(url, {}, status=401)
            if url == model_gateway.PROVIDER_URL + "/key":
                assert key in (KEY, ROTATED)
                return reply(url, {"data": {"is_management_key": False}})
            assert url == model_gateway.PROVIDER_URL + "/models/user"
            return reply(url, {"data": [{"id": MODEL}, {"id": MODEL + "-other"}]})

        def post(url, *, headers, timeout, trust_env, json):
            assert not trust_env
            if url.startswith(GATEWAY + "/"):
                response = gateway.post(url.removeprefix(GATEWAY), headers=headers, json=json)
                return reply(url, response.json(), status=response.status_code, method="POST")
            assert url == model_gateway.PROVIDER_URL + "/chat/completions"
            key = headers["Authorization"].split(" ", 1)[1]
            assert json["provider"]["allow_fallbacks"] is False
            assert json["messages"][-1]["content"] == '{"http-script": 1}'
            calls.append(("call", url, key))
            return reply(url, {"choices": [{"message": {"content": '{"priority":["http-script"]}'}}]}, method="POST")

        monkeypatch.setattr(httpx, "get", get)
        monkeypatch.setattr(httpx, "post", post)
        with TestClient(main.app, base_url=HOST) as admin, TestClient(main.app, base_url=HOST) as visitor:
            admin.cookies.set(SESSION_COOKIE, owner.cookies.get(SESSION_COOKIE))
            visitor.cookies.set(SESSION_COOKIE, outsider.cookies.get(SESSION_COOKIE))
            yield admin, visitor, gateway, ctx, calls, master


def root(ctx):
    return f"/api/platform/organizations/{ctx.org_id}/model-connection"


def setup_key(client, ctx, key=KEY, model=MODEL):
    values = {"model": model}
    if key is not None:
        values["api_key"] = key
    return client.put(root(ctx), json=values, headers=ORIGIN)


def project_root(ctx):
    return f"/api/platform/projects/{ctx.project_id}"


def state(ctx):
    with platform_session() as db:
        return db.execute(sa.select(connections.connections).where(
            connections.connections.c.org_id == ctx.org_id,
        )).mappings().first()


def test_model_setup_is_write_only_and_tenant_scoped(credential_platform, caplog):
    client, visitor, _, ctx, calls, _ = credential_platform
    path = root(ctx)
    assert client.get(path).json() == {"available": True, "connection": None}
    assert visitor.get(path).status_code == 404
    assert setup_key(visitor, ctx, ROTATED).status_code == 404
    assert visitor.delete(path, headers=ORIGIN).status_code == 404
    assert client.put(path, json={"model": MODEL, "api_key": KEY}).status_code == 403
    assert client.put(path, json={"model": MODEL, "api_key": KEY}, headers={"Origin": "https://other.test"}).status_code == 403
    assert setup_key(client, ctx, key=None).status_code == 422
    assert not calls
    connection = setup_key(client, ctx)
    assert connection.status_code == 200, connection.text
    assert connection.headers["Cache-Control"] == "no-store"
    summary = connection.json()["connection"]
    assert set(summary) == {"id", "provider", "base_url", "model", "verified_at", "source"}
    assert summary["model"] == MODEL and summary["verified_at"] and summary["source"] == "organization"
    assert client.get(path).json() == connection.json()
    row = state(ctx)
    assert isinstance(row["ciphertext"], bytes) and KEY.encode() not in row["ciphertext"]
    encryptor = connections.vault()
    assert connections.decrypt_key(encryptor, row["ciphertext"], ctx.org_id, row["generation"]) == KEY
    assert connections.decrypt_key(encryptor, row["ciphertext"], "a" * 32, row["generation"]) is None
    assert connections.decrypt_key(encryptor, row["ciphertext"], ctx.org_id, "a" * 32) is None
    assert KEY not in connection.text and KEY not in caplog.text
    assert [item[0] for item in calls] == ["verify", "verify"]


def test_managers_only_and_loopback_or_https_required(credential_platform):
    client, visitor, _, ctx, calls, _ = credential_platform
    visitor_id = visitor.get("/api/platform/auth/me").json()["id"]
    with platform_session() as db:
        db.add(Membership(org_id=ctx.org_id, user_id=visitor_id, role="analyst", joined_at=utc_now()))
    assert visitor.get(root(ctx)).status_code == 403
    assert setup_key(visitor, ctx).status_code == 403
    assert visitor.delete(root(ctx), headers=ORIGIN).status_code == 403
    assert not calls
    with TestClient(main.app, base_url="http://local-network.test") as unsafe:
        unsafe.cookies.set(SESSION_COOKIE, client.cookies.get(SESSION_COOKIE))
        assert unsafe.put(root(ctx), headers={"Origin": "http://local-network.test"},
                          json={"model": MODEL, "api_key": KEY}).status_code == 403
    with platform_session() as db:
        db.get(Membership, (ctx.org_id, visitor_id)).role = "admin"
    assert setup_key(visitor, ctx).status_code == 200
    assert client.get(root(ctx)).json()["connection"]["id"] == IDENTIFIER


def test_failed_rotation_leaves_connection_and_project_grant_active(credential_platform):
    client, _, _, ctx, calls, master = credential_platform
    assert setup_key(client, ctx).status_code == 200
    project = project_root(ctx)
    first = state(ctx)
    assert client.put(project + "/policy", json={"allowed_kinds": ["html"], "model_connection": IDENTIFIER}).status_code == 200
    assert setup_key(client, ctx, INVALID).status_code == 422
    master.rename(master.with_suffix(".offline"))
    assert setup_key(client, ctx, ROTATED).status_code == 503
    assert state(ctx) == first
    master.with_suffix(".offline").rename(master)
    assert setup_key(client, ctx, None, MODEL + "-missing").status_code == 422
    assert state(ctx) == first
    assert setup_key(client, ctx, ROTATED).status_code == 200
    latest = state(ctx)
    assert latest["generation"] != first["generation"] and latest["grant_id"] == first["grant_id"]
    assert client.get(project + "/scan-profile").json()["model_connection"]["model"] == MODEL
    assert client.get(project + "/scan-profile").json()["agent_path_enabled"] is False
    assert setup_key(client, ctx, None, MODEL + "-other").status_code == 200
    assert client.get(project + "/scan-profile").json()["model_connection"]["model"] == MODEL + "-other"
    assert not any(item[0] == "call" for item in calls)
    assert setup_key(client, ctx).status_code == 429


def _queue(client, ctx, label, version):
    return submit(client, ctx, {**artifact(), "scope_version": version,
                  "acknowledge_scope": True, "model_connection": IDENTIFIER}, key=label)


def _reserve(client, ctx, label, version=1):
    queued = _queue(client, ctx, label, version)
    assert queued.status_code == 202, queued.text
    scan_id = queued.json()["id"]
    ids = (ctx.org_id, ctx.project_id, scan_id)
    row = store.claim(*ids)
    current = store.reserve_model_connection(*ids, row["lease"])
    assert current is not None
    return {"org_id": ctx.org_id, "project_id": ctx.project_id, "scan_id": scan_id,
            "lease": row["lease"], "generation": current["generation"], "model": current["model"],
            "connection": IDENTIFIER, "counts": {"http-script": 1}}


def test_gateway_rechecks_revocation_and_refuses_replays(credential_platform):
    client, _, gateway, ctx, calls, _ = credential_platform
    headers = {"Authorization": "Bearer test-only-gateway-auth"}
    assert setup_key(client, ctx).status_code == 200
    project = project_root(ctx)
    policy = {"allowed_kinds": ["html"], "model_connection": IDENTIFIER}
    assert client.put(project + "/policy", json=policy).status_code == 200

    facts = _reserve(client, ctx, "pending-old-key")
    assert setup_key(client, ctx, ROTATED).status_code == 200
    assert gateway.post("/priority", json=facts, headers=headers).status_code == 409

    facts = _reserve(client, ctx, "granted-model")
    assert gateway.post("/priority", json={**facts, "org_id": "a" * 32}, headers=headers).status_code == 409
    assert gateway.post("/priority", json=facts, headers=headers).json() == {"priority": ["http-script"]}
    assert gateway.post("/priority", json=facts, headers=headers).status_code == 409

    facts = _reserve(client, ctx, "revoke-before-run")
    assert client.put(project + "/policy", json={**policy, "model_connection": None}).status_code == 200
    assert gateway.post("/priority", json=facts, headers=headers).status_code == 409

    assert client.put(project + "/policy", json=policy).status_code == 200
    facts = _reserve(client, ctx, "removed-before-run", version=3)
    removed = client.delete(root(ctx), headers=ORIGIN)
    assert removed.status_code == 200 and removed.json()["connection"] is None
    assert state(ctx) is None
    assert gateway.post("/priority", json=facts, headers=headers).status_code == 409
    assert _queue(client, ctx, "removed-connection", 3).status_code == 409
    assert setup_key(client, ctx).status_code == 200
    assert _queue(client, ctx, "old-grant-invalid", 3).status_code == 409
    assert client.get(project + "/scan-profile").json()["model_connection"] is None
    assert [call[-1] for call in calls if call[0] == "call"] == [ROTATED]


def test_invalid_requests_never_echo_credentials(credential_platform):
    client, _, gateway, ctx, _, _ = credential_platform
    invalid = "bad/secret/raw-token"
    response = setup_key(client, ctx, invalid)
    assert response.status_code == 422 and invalid not in response.text
    response = gateway.post("/verify", headers={"Authorization": "Bearer test-only-gateway-auth"},
                            json={"api_key": invalid, "model": MODEL, "org_id": ctx.org_id})
    assert response.status_code == 422 and invalid not in response.text
    response = submit(client, ctx, {**artifact(), "api_key": KEY})
    assert response.status_code == 422 and KEY not in response.text
    response = client.put(project_root(ctx) + "/policy", json={"allowed_kinds": ["html"], "api_key": KEY})
    assert response.status_code == 422 and KEY not in response.text


def test_gateway_transport_timeout_leaves_call_count_unknown(monkeypatch):
    monkeypatch.setenv("BASIRA_GATEWAY_URL", GATEWAY)
    monkeypatch.setenv("BASIRA_GATEWAY_TOKEN", "test-only-gateway-auth")
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("Synthetic gateway timeout")
    monkeypatch.setattr(model_gateway.httpx, "post", timeout)
    findings = [{"rule": "http-script"}, {"rule": "http-form"}]
    report = {"findings": findings.copy(), "metrics": {"modelCalls": 0}}
    model_gateway.enrich(report, {"model": MODEL, "generation": "a" * 32}, org_id="a" * 32,
                         project_id="b" * 32, scan_id="c" * 32, lease="d" * 32)
    assert report["enrichment"] == "fallback"
    assert report["findings"] == findings
    assert report["metrics"]["modelCalls"] is None


def test_other_provider_is_saved_and_a_stored_key_never_moves_to_another_target(credential_platform, monkeypatch):
    client, _, _, ctx, _, _ = credential_platform
    monkeypatch.setattr(model_gateway, "other_provider_models",
                        lambda provider, key, base_url=None: [{"id": "gpt-x", "name": "GPT X", "cost": "paid"}])
    saved = client.put(root(ctx), json={"provider": "openai", "model": "gpt-x", "api_key": KEY}, headers=ORIGIN)
    assert saved.status_code == 200, saved.text
    assert saved.json()["connection"]["provider"] == "openai"
    assert state(ctx)["provider"] == "openai" and KEY not in saved.text
    wrong_model = client.put(root(ctx), json={"provider": "openai", "model": "gpt-y", "api_key": KEY}, headers=ORIGIN)
    assert wrong_model.status_code == 422
    for target in ({"provider": "openrouter"}, {"provider": "custom", "base_url": "https://llm.example.com/v1"}):
        moved = client.put(root(ctx), json={"model": "gpt-x", **target}, headers=ORIGIN)
        assert moved.status_code == 422, moved.text
    assert client.put(root(ctx), json={"provider": "custom", "model": "gpt-x", "api_key": KEY}, headers=ORIGIN).status_code == 422


def test_unavailable_view_says_whether_the_gateway_is_missing_or_not_answering(monkeypatch):
    monkeypatch.delenv("BASIRA_GATEWAY_URL", raising=False)
    monkeypatch.delenv("BASIRA_GATEWAY_TOKEN", raising=False)
    assert connections.connection_view(None, False) == {
        "available": False, "connection": None, "reason": "not_configured"}
    monkeypatch.setenv("BASIRA_GATEWAY_URL", GATEWAY)
    monkeypatch.setenv("BASIRA_GATEWAY_TOKEN", "test-only-gateway-auth")
    assert connections.connection_view(None, False)["reason"] == "unreachable"
    assert "reason" not in connections.connection_view(None, True)
