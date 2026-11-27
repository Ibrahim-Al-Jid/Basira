"""Link completed source and web evidence reports within a project."""
from alembic import op
import sqlalchemy as sa

revision = "platform_evidence_links_0011"
down_revision = "platform_github_0010"
branch_labels = None
depends_on = None

TABLE = "project_evidence_links"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("org_id", sa.String(32), nullable=False),
        sa.Column("project_id", sa.String(32), nullable=False),
        sa.Column("code_scan", sa.String(32), nullable=False),
        sa.Column("web_scan", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        *[sa.ForeignKeyConstraint(
            ("org_id", "project_id", column),
            ("project_scan_provenance.org_id", "project_scan_provenance.project_id", "project_scan_provenance.scan_id"),
            ondelete="CASCADE",
        ) for column in ("code_scan", "web_scan")],
        sa.UniqueConstraint("org_id", "project_id", "code_scan", "web_scan", name="uq_evidence_links_pair"),
        sa.CheckConstraint("code_scan <> web_scan", name="ck_evidence_link_distinct"),
    )
    op.create_index("ix_evidence_links_web", TABLE, ["org_id", "project_id", "web_scan"])
    if op.get_context().dialect.name == "postgresql":
        scope = "org_id = current_setting('basira.org_id', true) AND project_id = current_setting('basira.project_id', true)"
        op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_scope ON {TABLE} USING ({scope}) WITH CHECK ({scope})")


def downgrade():
    op.drop_table(TABLE)
