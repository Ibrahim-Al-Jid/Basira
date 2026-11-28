"""Drop the unused `github_connections` table.

The table came with the personal workspace (0012) as a foundation for a read-only list of GitHub App
installations per account. No code ever wrote a row. The personal authorization now lives in
`personal_github_grants` and `personal_github_states` (0014), and a project's repository binding lives in
`project_github_sources` (0010). The only reader was `GET /api/platform/github-connections`, which always
returned an empty list with `connect_available: false`, and no client called it.

The table is dropped with its row level security policy and grants. The downgrade recreates it empty with
the same shape, check, policy and grant, so a code and schema rollback still works.
"""

import sqlalchemy as sa
from alembic import op

revision = "platform_drop_github_0035"
down_revision = "platform_drop_legacy_0034"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("github_connections")


def downgrade():
    op.create_table(
        "github_connections",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("installation_id", sa.String(32), primary_key=True),
        sa.Column("provider_account_id", sa.String(32), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('verified', 'revoked')", name="ck_github_connections_status"),
    )
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE github_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE github_connections FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY github_account_access ON github_connections FOR SELECT
        USING (user_id = current_setting('basira.owner_user_id', true))
    """)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                REVOKE ALL ON github_connections FROM basira_app;
                GRANT SELECT ON github_connections TO basira_app;
            END IF;
        END $$;
    """)
