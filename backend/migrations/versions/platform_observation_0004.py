"""Align historical finding memory with target-aware review fingerprints."""
import hashlib
import json

from alembic import op
import sqlalchemy as sa

revision = "platform_observation_0004"
down_revision = "platform_review_0003"
branch_labels = None
depends_on = None


def remap(forward):
    if op.get_context().as_sql:
        op.execute("-- Run this revision online to remap stored finding fingerprints.")
        return
    db = op.get_bind()
    if db.dialect.name == "postgresql":
        db.execute(sa.text("SET LOCAL row_security = off"))
    scans = sa.table("project_scans", sa.column("id"), sa.column("org_id"), sa.column("project_id"),
                     sa.column("report", sa.JSON), sa.column("policy", sa.JSON))
    findings = sa.table("project_finding_observations", sa.column("scan_id"), sa.column("org_id"),
                        sa.column("project_id"), sa.column("fingerprint"))
    statement = sa.select(scans).where(scans.c.report.is_not(None)).order_by(scans.c.id)
    for row in db.execute(statement.execution_options(yield_per=20)).mappings():
        report = row["report"] or {}
        artifact = report.get("input_artifact")
        if not artifact:
            continue
        target = (artifact["kind"], artifact["name"], (row["policy"] or {}).get("base_url"))
        matches = {(finding["rule"], finding.get("path")) for finding in report.get("findings", [])}
        for rule, path in matches:
            old = hashlib.sha256(f"{rule}\x00{path or ''}".encode()).hexdigest()
            new = hashlib.sha256(json.dumps((target, rule, path), ensure_ascii=True).encode()).hexdigest()
            original, migrated = (old, new) if forward else (new, old)
            db.execute(findings.update().where(
                findings.c.scan_id == row["id"], findings.c.org_id == row["org_id"],
                findings.c.project_id == row["project_id"], findings.c.fingerprint == original,
            ).values(fingerprint=migrated))


def upgrade():
    remap(True)


def downgrade():
    remap(False)
