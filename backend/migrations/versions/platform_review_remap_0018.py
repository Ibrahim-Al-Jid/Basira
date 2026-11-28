"""Move review status and activity onto the target-aware finding fingerprints.

Revision `platform_observation_0004` rewrote `project_finding_observations.fingerprint` but left the
`finding_reviews` and `finding_review_activity` rows on the older fingerprint, so every review recorded
before that revision stopped matching its finding. This revision applies the same mapping to both review
tables. It is idempotent: a fingerprint that already has a review is left alone, and scans without a
stored input artifact are skipped.
"""

import hashlib
import json

from alembic import op
import sqlalchemy as sa

revision = "platform_review_remap_0018"
down_revision = "platform_idempotency_0017"
branch_labels = None
depends_on = None


def fingerprints(rule, path, target):
    old = hashlib.sha256(f"{rule}\x00{path or ''}".encode()).hexdigest()
    new = hashlib.sha256(json.dumps((target, rule, path), ensure_ascii=True).encode()).hexdigest()
    return old, new


def remap(forward):
    if op.get_context().as_sql:
        op.execute("-- Run this revision online to move review rows onto the target-aware fingerprints.")
        return
    db = op.get_bind()
    if db.dialect.name == "postgresql":
        db.execute(sa.text("SET LOCAL row_security = off"))
    scans = sa.table("project_scans", sa.column("id"), sa.column("org_id"), sa.column("project_id"),
                     sa.column("report", sa.JSON), sa.column("policy", sa.JSON))
    reviews = sa.table("finding_reviews", sa.column("org_id"), sa.column("project_id"),
                       sa.column("fingerprint"), sa.column("status"))
    activity = sa.table("finding_review_activity", sa.column("org_id"), sa.column("project_id"),
                        sa.column("fingerprint"))
    observations = sa.table("project_finding_observations", sa.column("org_id"), sa.column("project_id"),
                            sa.column("scan_id"), sa.column("fingerprint"))
    statement = sa.select(scans).where(scans.c.report.is_not(None)).order_by(scans.c.id)
    for row in db.execute(statement.execution_options(yield_per=20)).mappings():
        report = row["report"] or {}
        artifact = report.get("input_artifact")
        if not artifact:
            continue
        target = (artifact["kind"], artifact["name"], (row["policy"] or {}).get("base_url"))
        pairs = set()
        for finding in report.get("findings", []):
            old, new = fingerprints(finding["rule"], finding.get("path"), target)
            pairs.add((old, new) if forward else (new, old))
        for source, destination in pairs:
            if source == destination:
                continue
            scope = {"org_id": row["org_id"], "project_id": row["project_id"], "fingerprint": destination}
            existing = db.execute(sa.select(reviews.c.fingerprint).where(
                reviews.c.org_id == row["org_id"], reviews.c.project_id == row["project_id"],
                reviews.c.fingerprint == source)).scalar_one_or_none()
            taken = db.execute(sa.select(reviews.c.fingerprint).where(
                reviews.c.org_id == row["org_id"], reviews.c.project_id == row["project_id"],
                reviews.c.fingerprint == destination)).scalar_one_or_none()
            if existing is None or taken is not None:
                continue
            # Only move a review when the scan itself already carries the destination fingerprint:
            # revision 0004 is what rewrites the observations, and this revision must not guess.
            pinned = db.execute(sa.select(observations.c.fingerprint).where(
                observations.c.org_id == row["org_id"], observations.c.project_id == row["project_id"],
                observations.c.scan_id == row["id"], observations.c.fingerprint == destination)).scalar_one_or_none()
            if pinned is None:
                continue
            # Copy the parent row first: activity rows keep a foreign key to it.
            db.execute(sa.insert(reviews).from_select(
                ["org_id", "project_id", "fingerprint", "status"],
                sa.select(reviews.c.org_id, reviews.c.project_id, sa.literal(destination), reviews.c.status).where(
                    reviews.c.org_id == row["org_id"], reviews.c.project_id == row["project_id"],
                    reviews.c.fingerprint == source),
            ))
            db.execute(activity.update().where(
                activity.c.org_id == row["org_id"], activity.c.project_id == row["project_id"],
                activity.c.fingerprint == source).values(fingerprint=destination))
            db.execute(reviews.delete().where(
                reviews.c.org_id == row["org_id"], reviews.c.project_id == row["project_id"],
                reviews.c.fingerprint == source))


def upgrade():
    remap(True)


def downgrade():
    remap(False)
