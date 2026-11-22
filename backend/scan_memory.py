"""Read only review categories for work on the same owner-scoped snapshot."""

from datetime import timedelta

import sqlalchemy as sa

from . import platform_runtime as store
from .advanced_reporting import activities, points, reviews
from .contracts import ReviewContext


REVIEW_CONTEXT_DAYS = 90
MAX_REVIEW_CONTEXT = 20


def restore_review_context(org_id, project_id, scan_id, lease, report):
    if not report.execution or not report.findings:
        return []
    with store.platform_session() as db:
        project = store.bind_job_project(db, org_id, project_id)
        if not project or not project.owner_user_id:
            return []
        current = store.select_scan(db, org_id, project_id, scan_id)
        if (not current or current["user_id"] != project.owner_user_id or current["state"] != "running"
                or current["lease"] != lease or current["lease_until"] <= store.now()):
            return []
        scope = db.execute(sa.select(store.provenance.c.scope).where(
            store.scope(store.provenance, org_id, project_id), store.provenance.c.scan_id == scan_id,
            store.provenance.c.source_sha256 == report.execution.source_sha256,
        )).scalar_one_or_none()
        if not scope:
            return []
        prior = db.execute(sa.select(store.scans.c.id).join(
            store.provenance, sa.and_(store.provenance.c.scan_id == store.scans.c.id,
                                      store.provenance.c.org_id == store.scans.c.org_id,
                                      store.provenance.c.project_id == store.scans.c.project_id),
        ).where(
            store.scope(store.scans, org_id, project_id), store.scans.c.id != scan_id,
            store.scans.c.user_id == current["user_id"], store.scans.c.state.in_(("completed", "partial")),
            store.scans.c.created_at >= store.now() - timedelta(days=REVIEW_CONTEXT_DAYS),
            store.provenance.c.source_sha256 == report.execution.source_sha256,
            store.provenance.c.scope["sha256"].as_string() == scope["sha256"],
        ).order_by(store.scans.c.created_at.desc(), store.scans.c.id).limit(1)).scalar_one_or_none()
        if not prior:
            return []
        current_points = points(report, current["policy"])
        prior_observation = sa.exists(sa.select(1).where(
            store.scope(store.findings, org_id, project_id), store.findings.c.scan_id == prior,
            store.findings.c.fingerprint == reviews.c.fingerprint,
        ))
        owner_review = sa.exists(sa.select(1).where(
            store.scope(activities, org_id, project_id), activities.c.fingerprint == reviews.c.fingerprint,
            activities.c.author_id == current["user_id"], activities.c.action == "status",
            activities.c.status == reviews.c.status,
            activities.c.created_at >= store.now() - timedelta(days=REVIEW_CONTEXT_DAYS),
        ))
        rows = db.execute(sa.select(reviews.c.fingerprint, reviews.c.status).where(
            store.scope(reviews, org_id, project_id),
            reviews.c.status.in_(("triaged", "resolved", "accepted")),
            reviews.c.fingerprint.in_(current_points), prior_observation, owner_review,
        ).order_by(reviews.c.fingerprint).limit(MAX_REVIEW_CONTEXT))
        return [ReviewContext(fingerprint=fingerprint, status=status, prior_scan_id=prior).model_dump(mode="json")
                for fingerprint, status in rows]
