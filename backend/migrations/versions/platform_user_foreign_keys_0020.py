"""Reference the identity table from the user columns added before it was referenced.

`project_scans.user_id`, `project_knowledge.reviewer_id`, `finding_review_activity.author_id` and
`project_legacy_reports.user_id` were plain strings, so a row could name a user that never existed.
The constraints are added `NOT VALID` first and validated only when the table holds no orphan, so the
migration cannot fail on a database that already drifted.
"""

from alembic import op
import sqlalchemy as sa

revision = "platform_user_foreign_keys_0020"
down_revision = "platform_retention_0019"
branch_labels = None
depends_on = None

COLUMNS = (
    ("project_scans", "user_id"),
    ("project_knowledge", "reviewer_id"),
    ("finding_review_activity", "author_id"),
    ("project_legacy_reports", "user_id"),
)


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    db = op.get_bind()
    for table, column in COLUMNS:
        name = f"fk_{table}_{column}_user"
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({column}) "
                   f"REFERENCES users(id) NOT VALID")
        orphans = db.execute(sa.text(
            f"SELECT count(*) FROM {table} AS row LEFT JOIN users AS owner ON owner.id = row.{column} "
            f"WHERE owner.id IS NULL")).scalar_one()
        if orphans == 0:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    for table, column in COLUMNS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT fk_{table}_{column}_user")
