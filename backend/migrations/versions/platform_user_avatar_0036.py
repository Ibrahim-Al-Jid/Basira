"""Store the account avatar on the user row so it follows the account across devices."""

from alembic import op
import sqlalchemy as sa

revision = "platform_user_avatar_0036"
down_revision = "platform_drop_github_0035"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("avatar", sa.Text()))


def downgrade():
    op.drop_column("users", "avatar")
