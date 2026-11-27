"""Add personal project ownership while preserving the previous foreign keys."""

from alembic import op
import sqlalchemy as sa

revision = "platform_personal_0012"
down_revision = "platform_evidence_links_0011"
branch_labels = None
depends_on = None

PROJECT_RECORDS = (
    "project_scans", "project_scan_events", "project_review_settings", "project_knowledge",
    "project_finding_observations", "project_legacy_reports", "finding_reviews",
    "finding_review_activity", "project_assets", "project_scan_provenance",
    "project_evidence_records", "project_evidence_links",
)


def upgrade():
    op.execute("ALTER TABLE organizations ADD COLUMN personal_owner_id VARCHAR(32) REFERENCES users(id)")
    op.create_index("ux_organizations_personal_owner", "organizations", ["personal_owner_id"], unique=True)
    op.execute("ALTER TABLE projects ADD COLUMN owner_user_id VARCHAR(32) REFERENCES users(id)")
    op.add_column("projects", sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.add_column("projects", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.create_index("ix_projects_owner_active", "projects", ["owner_user_id", "deleted_at"])
    op.create_table(
        "project_ownership_reviews",
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_ref", sa.String(160)),
    )
    op.create_table(
        "github_connections",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("installation_id", sa.String(32), primary_key=True),
        sa.Column("provider_account_id", sa.String(32), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('verified', 'revoked')", name="ck_github_connections_status"),
    )
    # Only an unshared project with one enabled owner can be transferred automatically.
    op.execute("""
        WITH sole_owners AS (
            SELECT m.org_id, MAX(m.user_id) AS user_id
            FROM memberships m JOIN users u ON u.id = m.user_id
            WHERE m.revoked_at IS NULL AND u.disabled_at IS NULL
            GROUP BY m.org_id
            HAVING COUNT(*) = 1 AND MAX(m.role) = 'owner'
        )
        UPDATE projects SET owner_user_id = (
            SELECT owner.user_id FROM sole_owners owner WHERE owner.org_id = projects.org_id
              AND NOT EXISTS (
                SELECT 1 FROM project_grants g
                WHERE g.org_id = projects.org_id AND g.project_id = projects.id
                  AND g.revoked_at IS NULL AND g.user_id <> owner.user_id
              )
        )
    """)
    op.execute("""
        INSERT INTO project_ownership_reviews (project_id, reason)
        SELECT p.id, CASE WHEN EXISTS (
            SELECT 1 FROM memberships m JOIN users u ON u.id = m.user_id
            WHERE m.org_id = p.org_id AND m.role = 'owner'
              AND m.revoked_at IS NULL AND u.disabled_at IS NULL
        ) THEN 'shared_membership_or_grant' ELSE 'missing_owner' END
        FROM projects p WHERE p.owner_user_id IS NULL
    """)
    if op.get_context().dialect.name != "postgresql":
        return
    for table in PROJECT_RECORDS:
        allowed = f"""EXISTS (
            SELECT 1 FROM public.projects p
            WHERE p.id = {table}.project_id AND p.org_id = {table}.org_id
              AND p.deleted_at IS NULL
              AND (current_setting('basira.legacy_project_access', true) = '1'
                OR p.owner_user_id = current_setting('basira.owner_user_id', true))
        )"""
        op.execute(f"CREATE POLICY personal_project_access ON {table} AS RESTRICTIVE "
                   f"USING ({allowed}) WITH CHECK ({allowed})")
    op.execute("ALTER TABLE github_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE github_connections FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY github_account_access ON github_connections FOR SELECT
        USING (user_id = current_setting('basira.owner_user_id', true))
    """)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                REVOKE ALL ON project_ownership_reviews, github_connections FROM basira_app;
                GRANT SELECT ON github_connections TO basira_app;
            END IF;
        END $$;
    """)


def downgrade():
    changed = op.get_bind().execute(sa.text("""
        SELECT EXISTS (SELECT 1 FROM organizations WHERE personal_owner_id IS NOT NULL)
            OR EXISTS (SELECT 1 FROM projects WHERE updated_at IS NOT NULL OR deleted_at IS NOT NULL)
            OR EXISTS (SELECT 1 FROM project_ownership_reviews WHERE resolved_at IS NOT NULL)
            OR EXISTS (SELECT 1 FROM github_connections)
    """)).scalar_one()
    if changed:
        raise RuntimeError("Personal project data exists. Restore a verified snapshot to roll back the schema.")
    if op.get_context().dialect.name == "postgresql":
        for table in PROJECT_RECORDS:
            op.execute(f"DROP POLICY personal_project_access ON {table}")
    op.drop_table("github_connections")
    op.drop_table("project_ownership_reviews")
    op.drop_index("ix_projects_owner_active", table_name="projects")
    op.drop_column("projects", "deleted_at")
    op.drop_column("projects", "updated_at")
    op.drop_column("projects", "owner_user_id")
    op.drop_index("ux_organizations_personal_owner", table_name="organizations")
    op.drop_column("organizations", "personal_owner_id")
