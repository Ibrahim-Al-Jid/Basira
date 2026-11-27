"""Add project-owned asset references and immutable scan provenance."""
from alembic import op
import sqlalchemy as sa

revision = "platform_provenance_0006"
down_revision = "platform_password_0005"
branch_labels = None
depends_on = None

TABLES = ("project_assets", "project_scan_provenance", "project_evidence_records")


def identifier(name, *, primary=False, nullable=False):
    return sa.Column(name, sa.String(32), primary_key=primary, nullable=nullable)


def scoped():
    return identifier("org_id", primary=True), identifier("project_id", primary=True)


def install_expiry():
    op.execute("""
        CREATE FUNCTION public.basira_expire_artifacts() RETURNS integer
        LANGUAGE SQL SECURITY DEFINER SET search_path = pg_catalog SET row_security = off
        AS $expiry$
            WITH expired AS (
                SELECT id FROM public.project_scans
                WHERE source_expires_at <= (statement_timestamp() AT TIME ZONE 'UTC')
                  AND raw IS NOT NULL AND state IN ('queued', 'running')
                ORDER BY source_expires_at
                LIMIT 100
                FOR UPDATE SKIP LOCKED
            ),
            updated AS (
                UPDATE public.project_scans AS scans
                SET state = 'failed', raw = NULL, lease = NULL, lease_until = NULL,
                    updated_at = (statement_timestamp() AT TIME ZONE 'UTC'), cursor = scans.cursor + 1
                FROM expired WHERE scans.id = expired.id
                RETURNING scans.id, scans.org_id, scans.project_id, scans.cursor, scans.updated_at
            ),
            logged AS (
                INSERT INTO public.project_scan_events
                  (org_id, project_id, scan_id, sequence, kind, detail, occurred_at)
                SELECT org_id, project_id, id, cursor, 'failed',
                       'انتهت مدة الاحتفاظ بالمدخل قبل اكتمال الفحص.', updated_at
                FROM updated
            ),
            delisted AS (
                DELETE FROM public.scan_dispatch_outbox
                USING updated WHERE scan_id = updated.id
            )
            SELECT count(*)::integer FROM updated;
        $expiry$;
    """)
    op.execute("REVOKE ALL ON FUNCTION public.basira_expire_artifacts() FROM PUBLIC")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_dispatch') THEN
                GRANT EXECUTE ON FUNCTION public.basira_expire_artifacts() TO basira_dispatch;
            END IF;
        END $$;
    """)


def upgrade():
    op.add_column("project_scans", sa.Column("source_expires_at", sa.DateTime))
    op.create_index("ix_project_scans_source_expiry", "project_scans", ["source_expires_at"])
    op.create_table(
        "project_assets", *scoped(), identifier("id", primary=True),
        sa.Column("reference_digest", sa.String(64), nullable=False),
        sa.Column("reference", sa.String(250), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id")),
        sa.UniqueConstraint("org_id", "project_id", "reference_digest", name="uq_project_assets_reference"),
    )
    op.create_table(
        "project_scan_provenance", *scoped(), identifier("scan_id", primary=True),
        identifier("asset_id", nullable=True), sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("scope", sa.JSON, nullable=False), sa.Column("tools", sa.JSON, nullable=False),
        sa.ForeignKeyConstraint(("org_id", "project_id", "scan_id"),
                                ("project_scans.org_id", "project_scans.project_id", "project_scans.id"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(("org_id", "project_id", "asset_id"),
                                ("project_assets.org_id", "project_assets.project_id", "project_assets.id")),
    )
    op.create_table(
        "project_evidence_records", *scoped(), identifier("scan_id", primary=True),
        sa.Column("ordinal", sa.Integer, primary_key=True), sa.Column("rule", sa.String(60), nullable=False),
        sa.Column("line", sa.Integer, nullable=False), sa.Column("path", sa.String(240)),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(("org_id", "project_id", "scan_id"),
                                ("project_scan_provenance.org_id", "project_scan_provenance.project_id",
                                 "project_scan_provenance.scan_id"), ondelete="CASCADE"),
    )
    if op.get_context().dialect.name == "postgresql":
        op.execute("SET LOCAL row_security = off")
        op.execute("UPDATE project_scans SET source_expires_at = created_at + interval '15 minutes' WHERE raw IS NOT NULL")
        filter_ = "org_id = current_setting('basira.org_id', true) AND project_id = current_setting('basira.project_id', true)"
        for name in TABLES:
            op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY project_access ON {name} USING ({filter_}) WITH CHECK ({filter_})")
        op.execute("""
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                    REVOKE UPDATE, DELETE ON project_assets, project_scan_provenance,
                    project_evidence_records FROM basira_app;
                END IF;
            END $$;
        """)
        install_expiry()
    else:
        op.execute("UPDATE project_scans SET source_expires_at = datetime(created_at, '+15 minutes') WHERE raw IS NOT NULL")


def downgrade():
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP FUNCTION public.basira_expire_artifacts()")
    for name in reversed(TABLES):
        op.drop_table(name)
    op.drop_index("ix_project_scans_source_expiry", table_name="project_scans")
    op.drop_column("project_scans", "source_expires_at")
