"""Drop the table that held pre-platform session reports.

`project_legacy_reports` stored a report a person had produced in the anonymous lab before signing in,
once they saved it into a project. The lab and its SQLite report store are gone (#188), and the readers
that could still reach this table are removed with it, so the table holds nothing that any code reads
or writes.

The rows are reports of tests and the owner confirmed none of them needs keeping, so this is a drop and
not a data migration. The table carries row level security, two policies, an index and two foreign
keys; PostgreSQL drops all of them with the table.

The downgrade recreates the empty table with the same shape, index, policies, foreign keys and grants,
so a rollback of the code and the migration together still works. It cannot restore rows: take a
`pg_dump -t project_legacy_reports -Fc` before running this where the table might still hold any.
"""

import sqlalchemy as sa
from alembic import op

revision = "platform_drop_legacy_0034"
down_revision = "platform_agent_calls_0033"
branch_labels = None
depends_on = None

PROJECT_ACCESS = """org_id = current_setting('basira.org_id', true)
    AND project_id = current_setting('basira.project_id', true)"""

PERSONAL_ACCESS = """EXISTS (
        SELECT 1 FROM public.projects p
        WHERE p.id = project_legacy_reports.project_id
          AND p.org_id = project_legacy_reports.org_id
          AND p.deleted_at IS NULL
          AND (current_setting('basira.legacy_project_access', true) = '1'
               OR p.owner_user_id = current_setting('basira.owner_user_id', true))
    )"""


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.drop_table("project_legacy_reports")


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.create_table(
        "project_legacy_reports",
        sa.Column("legacy_id", sa.String(32), primary_key=True),
        sa.Column("org_id", sa.String(32), nullable=False),
        sa.Column("project_id", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("report_index", sa.JSON(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id"),
                               name="project_legacy_reports_org_id_project_id_fkey"),
        sa.ForeignKeyConstraint(("user_id",), ("users.id",),
                               name="fk_project_legacy_reports_user_id_user"),
    )
    op.create_index("ix_legacy_reports_scope", "project_legacy_reports", ["org_id", "project_id"])
    op.execute("ALTER TABLE project_legacy_reports ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_legacy_reports FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY project_access ON project_legacy_reports USING ({PROJECT_ACCESS}) "
               f"WITH CHECK ({PROJECT_ACCESS})")
    op.execute(f"CREATE POLICY personal_project_access ON project_legacy_reports AS RESTRICTIVE "
               f"USING ({PERSONAL_ACCESS}) WITH CHECK ({PERSONAL_ACCESS})")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON project_legacy_reports TO basira_app;
            END IF;
        END $$;
    """)
