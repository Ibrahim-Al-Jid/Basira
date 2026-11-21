"""Add hashed, expiring organization invitations."""
from alembic import op
import sqlalchemy as sa

revision = "platform_invitations_0007"
down_revision = "platform_provenance_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("org_id", sa.String(32), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_digest", sa.String(64), unique=True, nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role in ('admin', 'analyst', 'viewer')", name="ck_organization_invitations_role"),
    )
    op.create_index(
        "ix_organization_invitations_org_expiry",
        "organization_invitations",
        ["org_id", "expires_at"],
    )


def downgrade():
    op.drop_table("organization_invitations")
