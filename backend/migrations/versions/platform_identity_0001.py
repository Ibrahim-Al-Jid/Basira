"""Create verified identities and tenant organization/project grants."""

from alembic import op
import sqlalchemy as sa

revision = "platform_identity_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_digest", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("expires_at > created_at", name="ck_auth_sessions_expiry"),
    )
    op.create_index("ix_auth_sessions_user", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expiry", "auth_sessions", ["expires_at"])
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "memberships",
        sa.Column("org_id", sa.String(32), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role in ('owner', 'admin', 'analyst', 'viewer')", name="ck_memberships_role"),
    )
    op.create_index("ix_memberships_user", "memberships", ["user_id"])
    op.create_table(
        "projects",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("org_id", sa.String(32), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "id", name="uq_projects_org_id"),
    )
    op.create_index("ix_projects_org", "projects", ["org_id"])
    op.create_table(
        "project_grants",
        sa.Column("org_id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), primary_key=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"], ["projects.org_id", "projects.id"],
            name="fk_project_grants_project",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "user_id"], ["memberships.org_id", "memberships.user_id"],
            name="fk_project_grants_membership",
        ),
    )
    op.create_index("ix_project_grants_membership", "project_grants", ["org_id", "user_id"])


def downgrade():
    for table in ("project_grants", "projects", "memberships", "organizations", "auth_sessions", "users"):
        op.drop_table(table)
