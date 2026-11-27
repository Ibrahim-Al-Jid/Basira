"""Add project-scoped GitHub App attachment metadata."""
from alembic import op
import sqlalchemy as sa

revision = "platform_github_0010"
down_revision = "platform_profiles_0009"
branch_labels = None
depends_on = None

TABLE = "project_github_sources"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("org_id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), primary_key=True),
        sa.Column("id", sa.String(32), nullable=False, unique=True),
        sa.Column("installation_id", sa.BigInteger, nullable=False),
        sa.Column("repository_id", sa.BigInteger, nullable=False),
        sa.Column("repository", sa.String(140), nullable=False),
        sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id"), ondelete="CASCADE"),
    )
    if op.get_context().dialect.name == "postgresql":
        org = "org_id = current_setting('basira.org_id', true)"
        project = "project_id = current_setting('basira.project_id', true)"
        op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY listing ON {TABLE} FOR SELECT USING ({org} AND "
                   f"({project} OR current_setting('basira.project_id', true) = ''))")
        op.execute(f"CREATE POLICY changes ON {TABLE} FOR ALL USING ({org} AND {project}) "
                   f"WITH CHECK ({org} AND {project})")


def downgrade():
    op.drop_table(TABLE)
