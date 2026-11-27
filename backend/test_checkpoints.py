"""Lease-fenced persistence tests for a redacted scan checkpoint."""

from datetime import timedelta
import hashlib
import json

import pytest
import sqlalchemy as sa

from . import platform_jobs as jobs, platform_runtime as store
from .platform_db import platform_session
from .test_platform_runtime import artifact, platform, submit  # noqa: F401


def scan_row(scan_id):
    with platform_session() as db:
        return db.execute(sa.select(store.scans).where(store.scans.c.id == scan_id)).mappings().one()


def expire_lease(scan_id):
    with platform_session() as db:
        db.execute(store.scans.update().where(store.scans.c.id == scan_id)
                   .values(lease_until=store.now() - timedelta(seconds=1)))


def test_retry_reuses_checkpoint_without_reprocessing_source(platform, monkeypatch):
    owner, stranger, ctx = platform
    raw = b'<script src="http://assets.test/main.js"></script>'
    created = submit(owner, ctx, artifact(content=raw))
    assert created.status_code == 202
    scan_id = created.json()["id"]
    ids = (ctx.org_id, ctx.project_id, scan_id)
    attempts = []
    original = jobs.analyzed

    def analyzed(row, *more):
        attempts.append(row["lease"])
        return original(row, *more)

    def stopped_before_publish(*_args, **_kwargs):
        raise RuntimeError("Lost worker before report publication")

    monkeypatch.setattr(jobs, "analyzed", analyzed)
    with monkeypatch.context() as crashed:
        crashed.setattr(store, "finish", stopped_before_publish)
        with pytest.raises(RuntimeError, match="Lost worker"):
            jobs.execute_scan(*ids)
    first = scan_row(scan_id)
    checkpoint = first["analysis_checkpoint"]
    assert first["state"] == "running" and first["report"] is None
    assert checkpoint["analysis"]["execution"]["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert checkpoint["analysis"]["execution"]["trace_id"] == scan_id
    assert set(checkpoint["analysis"]) <= store.ANALYSIS_RESULT_FIELDS
    assert "assets.test" not in json.dumps(checkpoint)

    expire_lease(scan_id)
    jobs.execute_scan(*ids)
    assert len(attempts) == 1
    closed = scan_row(scan_id)
    assert closed["state"] == "completed" and closed["attempt"] == 2
    assert closed["raw"] is None and closed["analysis_checkpoint"] is None
    assert {"http-script"} == {finding["rule"] for finding in closed["report"]["findings"]}
    route = f"/api/platform/projects/{ctx.project_id}/reports/{scan_id}"
    assert owner.get(route).status_code == 200
    assert stranger.get(route).status_code == 404
    with platform_session() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(store.evidence_records)
                         .where(store.evidence_records.c.scan_id == scan_id)) == 1


def test_checkpoint_rejects_stale_lease_and_other_artifact_and_clears_on_cancel(platform):
    owner, _, ctx = platform
    scan_id = submit(owner, ctx).json()["id"]
    ids = (ctx.org_id, ctx.project_id, scan_id)
    first = store.claim(*ids)
    analysis = jobs.analyzed(first)["result"]
    mistaken = {**analysis, "execution": {**analysis["execution"], "source_sha256": "0" * 64}}
    with pytest.raises(ValueError, match="Invalid deterministic analysis"):
        store.save_analysis_checkpoint(*ids, first["lease"], mistaken)
    assert scan_row(scan_id)["analysis_checkpoint"] is None
    expire_lease(scan_id)
    second = store.claim(*ids)
    assert store.save_analysis_checkpoint(*ids, first["lease"], analysis) is None
    assert store.save_analysis_checkpoint(*ids, second["lease"], {
        **analysis, "raw": "untrusted-projection-extra", "checkpoint_state": "untrusted-projection-extra",
    })
    assert "untrusted-projection-extra" not in json.dumps(scan_row(scan_id)["analysis_checkpoint"])
    route = f"/api/platform/projects/{ctx.project_id}/scans/{scan_id}/cancel"
    assert owner.post(route).json()["state"] == "cancelled"
    assert scan_row(scan_id)["analysis_checkpoint"] is None


def test_checkpoint_expires_with_source_and_rejects_modified_report(platform):
    owner, _, ctx = platform
    scan_id = submit(owner, ctx).json()["id"]
    ids = (ctx.org_id, ctx.project_id, scan_id)
    first = store.claim(*ids)
    analysis = jobs.analyzed(first)["result"]
    store.save_analysis_checkpoint(*ids, first["lease"], analysis)
    checkpoint = scan_row(scan_id)["analysis_checkpoint"]
    checkpoint["analysis"]["summary_en"] = "Modified after checkpoint"
    with platform_session() as db:
        db.execute(store.scans.update().where(store.scans.c.id == scan_id).values(analysis_checkpoint=checkpoint))
    expire_lease(scan_id)
    second = store.claim(*ids)
    assert second["analysis_checkpoint"] is None and scan_row(scan_id)["analysis_checkpoint"] is None

    store.save_analysis_checkpoint(*ids, second["lease"], analysis)
    with platform_session() as db:
        db.execute(store.scans.update().where(store.scans.c.id == scan_id)
                   .values(source_expires_at=store.now() - timedelta(seconds=1)))
    assert store.expire_pending_artifacts() == 1
    expired = scan_row(scan_id)
    assert expired["state"] == "failed" and expired["analysis_checkpoint"] is None and expired["raw"] is None


def test_publication_cannot_replace_checkpoint_evidence(platform, monkeypatch):
    owner, _, ctx = platform
    scan_id = submit(owner, ctx).json()["id"]
    ids = (ctx.org_id, ctx.project_id, scan_id)
    finish = store.finish

    def replace_evidence(*args, report=None, **kwargs):
        report["findings"][0]["evidence"] = "Invented after validation"
        return finish(*args, report=report, **kwargs)

    with monkeypatch.context() as altered:
        altered.setattr(store, "finish", replace_evidence)
        jobs.execute_scan(*ids)
    held = scan_row(scan_id)
    assert held["state"] == "running" and held["report"] is None
    assert "Invented after validation" not in json.dumps(held["analysis_checkpoint"])

    expire_lease(scan_id)
    jobs.execute_scan(*ids)
    assert scan_row(scan_id)["state"] == "completed"
