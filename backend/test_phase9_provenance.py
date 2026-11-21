import hashlib
from datetime import timedelta

import httpx
import sqlalchemy as sa

from . import phase9_contracts, platform_jobs as jobs, platform_runtime as store
from .artifact_review import RULESET_VERSION, catalog
from .platform_db import platform_session
from .test_platform_runtime import artifact, platform, submit  # noqa: F401


def root(ctx):
    return f"/api/platform/projects/{ctx.project_id}"


def reviewed(version, **extra):
    return {**artifact(), "scope_version": version, "acknowledge_scope": True, **extra}


def test_scoped_snapshot_pins_policy_and_tool_versions(platform):
    owner, stranger, ctx = platform
    path = root(ctx)
    original = owner.get(path + "/scan-profile").json()
    assert original["allowed_kinds"] == ["html"]
    assert original["scope_version"] == 0
    assert original["mode"] == "offline"
    assert {tool["id"] for tool in original["tools_by_input"]["html"]} == {
        "html-attributes", "browser-controls", "browser-controls-extra",
    }
    assert not original["asset_linked"]
    assert stranger.get(path + "/scan-profile").status_code == 404
    assert submit(owner, ctx, reviewed(0, acknowledge_scope=False)).status_code == 422
    target = {"allowed_kinds": ["html"], "base_url": "https://host.test/private/project", "expected_version": 0}
    assert owner.put(path + "/policy", json=target).status_code == 200
    assert owner.put(path + "/policy", json=target).status_code == 409
    assert submit(owner, ctx, reviewed(0)).status_code == 409
    result = submit(owner, ctx, reviewed(1))
    assert result.status_code == 202, result.text
    scan_id = result.json()["id"]
    scan_path = f"{path}/scans/{scan_id}"
    meta = owner.get(scan_path + "/provenance").json()
    assert meta["scope"]["version"] == 1
    assert meta["scope"]["ruleset_version"] == RULESET_VERSION
    assert meta["snapshot"]["sha256"] == hashlib.sha256(b'<script src="http://assets.test/main.js"></script>').hexdigest()
    assert meta["asset"]["id"] == meta["scope"]["asset_id"]
    assert meta["asset"]["source"] == "project_policy"
    assert meta["asset"]["reference"] == "https://host.test"
    assert "private/project" not in str(meta)
    assert {tool["id"] for tool in meta["tools"]} == {"html-attributes", "browser-controls", "browser-controls-extra"}
    assert stranger.get(scan_path + "/provenance").status_code == 404
    assert stranger.get(scan_path + "/evidence").status_code == 404

    assert owner.put(path + "/policy", json={**target, "expected_version": 1, "base_url": "https://different.test"}).status_code == 200
    assert submit(owner, ctx, reviewed(1)).json()["id"] == scan_id  # Idempotent retries return the reviewed scan.
    assert submit(owner, ctx, reviewed(1), key="different-key").status_code == 409
    jobs.execute_scan(ctx.org_id, ctx.project_id, scan_id)
    finished = owner.get(scan_path + "/provenance").json()
    assert finished == {**meta, "evidence_count": 1}
    finding = owner.get(scan_path + "/evidence").json()[0]
    assert finding["rule"] == "http-script"
    assert finding["path"] == "release.html"
    assert finding["line"] == 1
    assert "assets.test" not in str(finding)
    assert owner.get(scan_path + "/evidence", params={"offset": 1}).json() == []
    report = owner.get(path + "/reports/" + scan_id).json()
    assert "Found 1 finding type at 1 location." in report["summary_en"]
    assert {row["rule"] for row in report["coverage"]} == {row["id"] for row in catalog()["rules"]}
    assert set(run["tool"] for run in report["task_runs"] if run["agent"] == "analysis") == {
        "html-attributes", "browser-controls", "browser-controls-extra",
    }
    assert all(row["version"] == RULESET_VERSION for row in report["task_runs"] if row["agent"] == "analysis")


def test_technical_manifests_and_provenance_access_follow_project_grants(platform):
    owner, other, ctx = platform
    path = root(ctx)
    scan_id = submit(owner, ctx, reviewed(0)).json()["id"]
    status = owner.get(path + "/technical").json()
    assert set(status["permissions"]) == {"owner", "admin", "analyst", "viewer"}
    assert status["permissions"]["viewer"] == ["export", "read"]
    assert len(status["roles"]) == 5
    assert len(status["tools"]) == 14
    manifests = {tool["id"]: tool for tool in status["tools"]}
    assert all(tool in manifests for role in status["roles"] for tool in role["tools"])
    assert "html" not in manifests["dependency-evidence"]["supported_inputs"]
    assert all(not role["network"] for role in status["roles"])
    user_id = other.get("/api/platform/auth/me").json()["id"]
    members = f"/api/platform/organizations/{ctx.org_id}/members"
    assert owner.post(members, json={"user_id": user_id, "role": "viewer"}).status_code == 200
    grants = path + "/grants"
    assert owner.post(grants, json={"user_id": user_id}).status_code == 200
    assert other.get(path + "/technical").status_code == 403
    assert other.get(path + "/scans/" + scan_id + "/provenance").status_code == 200
    assert submit(other, ctx, reviewed(0)).status_code == 403
    assert owner.delete(grants + "/" + user_id).status_code == 204
    assert other.get(path + "/scans/" + scan_id + "/provenance").status_code == 404


def test_expiry_clears_raw_source_and_outbox_without_deleting_history(platform):
    owner, _, ctx = platform
    path = root(ctx)
    first = submit(owner, ctx, reviewed(0)).json()["id"]
    assert store.claim(ctx.org_id, ctx.project_id, first)
    second = submit(owner, ctx, reviewed(0), key="expiring-source").json()["id"]
    with platform_session() as db:
        db.execute(store.scans.update().values(source_expires_at=store.now() - timedelta(seconds=1)))
    assert store.claim(ctx.org_id, ctx.project_id, first) is None
    assert store.expire_pending_artifacts() == 1
    assert store.expire_pending_artifacts() == 0
    with platform_session() as db:
        assert db.execute(sa.select(store.scans.c.raw)).scalars().all() == [None, None]
        assert db.execute(sa.select(store.dispatch)).all() == []
    for scan_id in (first, second):
        status = owner.get(f"{path}/scans/{scan_id}").json()
        assert status["state"] == "failed"
        assert status["events"][-1]["detail"] == store.EXPIRED_MESSAGE
        assert owner.get(f"{path}/scans/{scan_id}/provenance").status_code == 200


def test_changed_raw_snapshot_fails_closed_before_analysis(platform):
    owner, _, ctx = platform
    scan_id = submit(owner, ctx, reviewed(0)).json()["id"]
    with platform_session() as db:
        db.execute(store.scans.update().where(store.scans.c.id == scan_id).values(raw=b"<p>Changed source</p>"))
    assert store.claim(ctx.org_id, ctx.project_id, scan_id) is None
    status = owner.get(f"{root(ctx)}/scans/{scan_id}").json()
    assert status["state"] == "failed"
    assert status["events"][-1]["detail"] == store.INVALID_PROVENANCE_MESSAGE


def test_missing_eligible_adapter_is_skipped_without_changing_the_catalog(platform, monkeypatch):
    owner, _, ctx = platform
    path = root(ctx)
    load = phase9_contracts.import_module

    def unavailable(name, package):
        if name == ".checks.web":
            raise ImportError("Not installed in the test image")
        return load(name, package)

    monkeypatch.setattr(phase9_contracts, "import_module", unavailable)
    profile = owner.get(path + "/scan-profile").json()
    assert "browser-controls" not in {tool["id"] for tool in profile["tools_by_input"]["html"]}
    registry = owner.get(path + "/technical").json()
    status = next(tool for tool in registry["tools"] if tool["id"] == "browser-controls")
    assert status["status"] == "disabled"
    assert status["reason"] == "adapter_unavailable"
    scan_id = submit(owner, ctx, reviewed(0)).json()["id"]
    jobs.execute_scan(ctx.org_id, ctx.project_id, scan_id)
    report = owner.get(path + "/reports/" + scan_id).json()
    assert report["status"] == "partial"
    assert len(report["coverage"]) == 100
    assert len([rule for rule in report["coverage"] if rule["status"] == "skipped"]) == 17
    assert any(rule["reason"] == "unsupported_input" for rule in report["coverage"])


def test_model_requires_reviewed_connection_and_can_be_disabled_before_reservation(platform, monkeypatch):
    owner, stranger, ctx = platform
    path = root(ctx)
    monkeypatch.setenv("MARSAD_PROJECT_MODEL_ENABLED", "1")
    monkeypatch.setenv("MARSAD_OPENROUTER_MODEL", "approved/defensive")
    from . import model_connections
    monkeypatch.setattr(model_connections, "connection_is_ready", lambda connection: connection is not None)
    choose = {"allowed_kinds": ["html"], "model_connection": "openrouter-default"}
    assert stranger.put(path + "/policy", json=choose).status_code == 404
    assert submit(owner, ctx, reviewed(0, model_connection="openrouter-default"), key="model-disallowed").status_code == 409
    assert owner.put(path + "/policy", json=choose).status_code == 200
    assert owner.get(path + "/scan-profile").json()["model_connection"]["max_calls"] == 1
    legacy = submit(owner, ctx, {**artifact(), "enrich": True}, key="legacy-model")
    assert not legacy.json()["artifact"]["enrich"]
    accepted = submit(owner, ctx, reviewed(1, model_connection="openrouter-default"))
    assert accepted.status_code == 202, accepted.text
    scan_id = accepted.json()["id"]
    assert accepted.json()["artifact"]["enrich"]
    assert "connection_model" not in accepted.json()["artifact"]
    ids = (ctx.org_id, ctx.project_id, scan_id)
    claimed = store.claim(*ids)
    assert store.reserve_model_connection(*ids, claimed["lease"])["model"] == "approved/defensive"
    assert store.reserve_model_connection(*ids, claimed["lease"]) is None
    second = submit(owner, ctx, reviewed(1, model_connection="openrouter-default"), key="pending-model").json()["id"]
    second_ids = (ctx.org_id, ctx.project_id, second)
    later = store.claim(*second_ids)
    assert owner.put(path + "/policy", json={**choose, "model_connection": None}).status_code == 200
    assert store.reserve_model_connection(*second_ids, later["lease"]) is None
    assert owner.get(path + "/scan-profile").json()["model_connection"] is None


def test_disabling_scan_actor_revokes_provider_budget(platform, monkeypatch):
    from .platform_db import User, utc_now

    owner, _, ctx = platform
    monkeypatch.setenv("MARSAD_PROJECT_MODEL_ENABLED", "1")
    monkeypatch.setenv("MARSAD_OPENROUTER_MODEL", "approved/defensive")
    assert owner.put(root(ctx) + "/policy", json={
        "allowed_kinds": ["html"], "model_connection": "openrouter-default",
    }).status_code == 200
    scan_id = submit(owner, ctx, reviewed(1, model_connection="openrouter-default")).json()["id"]
    ids = (ctx.org_id, ctx.project_id, scan_id)
    claimed = store.claim(*ids)
    with platform_session() as db:
        db.execute(sa.update(User).where(User.id == claimed["user_id"]).values(disabled_at=utc_now()))
    assert store.reserve_model_connection(*ids, claimed["lease"]) is None


def test_worker_records_model_when_authorized_and_preserves_evidence(platform, monkeypatch):
    owner, _, ctx = platform
    path = root(ctx)
    monkeypatch.setenv("MARSAD_PROJECT_MODEL_ENABLED", "1")
    monkeypatch.setenv("MARSAD_OPENROUTER_MODEL", "approved/defensive")
    monkeypatch.setenv("MARSAD_GATEWAY_URL", "http://gateway.test")
    monkeypatch.setenv("MARSAD_GATEWAY_TOKEN", "internal-fixture-token")
    assert owner.put(path + "/policy", json={
        "allowed_kinds": ["html"], "model_connection": "openrouter-default",
    }).status_code == 200
    def offline(*args, **kwargs):
        raise httpx.ConnectError("Gateway offline")

    monkeypatch.setattr(httpx, "get", offline)
    assert owner.get(path + "/scan-profile").json()["model_connection"] is None

    def health(url, *, headers, timeout, trust_env):
        assert not trust_env
        assert url == "http://gateway.test/health"
        assert headers == {"Authorization": "Bearer internal-fixture-token"}
        return httpx.Response(200, request=httpx.Request("GET", url),
                              json={"ready": True, "model": "approved/defensive"})

    def reply(url, *, headers, timeout, json, trust_env):
        assert not trust_env
        assert url == "http://gateway.test/priority"
        assert headers == {"Authorization": "Bearer internal-fixture-token"}
        assert json == {"connection": "openrouter-default", "model": "approved/defensive",
                        "counts": {"http-script": 1}}
        return httpx.Response(200, request=httpx.Request("POST", url), json={"priority": ["http-script"]})

    monkeypatch.setattr(httpx, "get", health)
    monkeypatch.setattr(httpx, "post", reply)
    assert owner.get(path + "/scan-profile").json()["enrichment_available"]
    model_id = submit(owner, ctx, reviewed(1, model_connection="openrouter-default"), key="provider-scan").json()["id"]
    local_id = submit(owner, ctx, reviewed(1), key="deterministic-scan").json()["id"]
    for scan_id in (model_id, local_id):
        jobs.execute_scan(ctx.org_id, ctx.project_id, scan_id)
    accelerated = owner.get(path + "/reports/" + model_id)
    deterministic = owner.get(path + "/reports/" + local_id)
    assert accelerated.status_code == deterministic.status_code == 200
    result, baseline = accelerated.json(), deterministic.json()
    assert result["model"] == "approved/defensive"
    assert result["enrichment"] == "model" and result["metrics"]["modelCalls"] == 1
    assert result["findings"] == baseline["findings"]
    assert result["coverage"] == baseline["coverage"]
    assert "internal-fixture-token" not in accelerated.text
