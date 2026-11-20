"""Add scoped review status and append-only activity."""
from alembic import op
import sqlalchemy as sa

revision = "platform_review_0003"
down_revision = "platform_runtime_0002"
branch_labels = None
depends_on = None


def scope_columns(primary=False):
    return (
        sa.Column("org_id", sa.String(32), nullable=False, primary_key=primary),
        sa.Column("project_id", sa.String(32), nullable=False, primary_key=primary),
        sa.Column("fingerprint", sa.String(64), nullable=False, primary_key=primary),
    )


def upgrade():
    op.create_table("finding_reviews", *scope_columns(True), sa.Column("status", sa.String(16), nullable=False),
                    sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id")),
                    sa.CheckConstraint("status IN ('open','triaged','resolved','accepted')",
                                       name="ck_finding_reviews_status"))
    op.create_table(
        "finding_review_activity", *scope_columns(), sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("author_id", sa.String(32), nullable=False), sa.Column("author", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("action", sa.String(12), nullable=False),
        sa.Column("status", sa.String(16)), sa.Column("previous", sa.String(16)), sa.Column("body", sa.String(2000)),
        sa.ForeignKeyConstraint(("org_id", "project_id", "fingerprint"),
                                ("finding_reviews.org_id", "finding_reviews.project_id", "finding_reviews.fingerprint"),
                                ondelete="CASCADE"),
    )
    op.create_index("ix_review_activity_timeline", "finding_review_activity",
                    ["org_id", "project_id", "fingerprint", "created_at"])
    if op.get_context().dialect.name == "postgresql":
        clause = "org_id = current_setting('marsad.org_id', true) AND project_id = current_setting('marsad.project_id', true)"
        for table in ("finding_reviews", "finding_review_activity"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY project_access ON {table} USING ({clause}) WITH CHECK ({clause})")


def downgrade():
    op.drop_table("finding_review_activity")
    op.drop_table("finding_reviews")
