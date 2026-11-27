"""Record which model provider a saved connection uses; the key and the authoritative address stay sealed."""

from alembic import op
import sqlalchemy as sa

revision = "platform_providers_0016"
down_revision = "platform_checkpoints_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organization_model_connections",
                  sa.Column("provider", sa.String(32), nullable=False, server_default="openrouter"))
    op.add_column("organization_model_connections", sa.Column("base_url", sa.String(300)))


def downgrade():
    op.drop_column("organization_model_connections", "base_url")
    op.drop_column("organization_model_connections", "provider")
