"""Store profile names and a unique optional username without altering login identity."""
from alembic import op
import sqlalchemy as sa

revision = "platform_profiles_0009"
down_revision = "platform_models_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("first_name", sa.String(80)))
    op.add_column("users", sa.Column("last_name", sa.String(80)))
    op.add_column("users", sa.Column("username", sa.String(30)))
    op.create_index("ux_users_username", "users", ["username"], unique=True)
    op.execute("UPDATE users SET display_name = '' WHERE issuer = 'urn:basira:password' AND display_name = subject")


def downgrade():
    op.execute("UPDATE users SET display_name = subject WHERE issuer = 'urn:basira:password' AND display_name = ''")
    op.drop_index("ux_users_username", table_name="users")
    op.drop_column("users", "username")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
