"""Add local password identities and fixed-window authentication throttles."""
from alembic import op
import sqlalchemy as sa

revision = "platform_password_0005"
down_revision = "platform_observation_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("password_credentials",
                    sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
                    sa.Column("password_hash", sa.String(255), nullable=False))
    op.create_table("password_attempt_limits", sa.Column("scope", sa.String(80), primary_key=True),
                    sa.Column("window", sa.BigInteger, primary_key=True),
                    sa.Column("attempts", sa.Integer, nullable=False))
    op.create_index("ix_password_attempt_limits_window", "password_attempt_limits", ["window"])


def downgrade():
    op.drop_table("password_attempt_limits")
    op.drop_table("password_credentials")
