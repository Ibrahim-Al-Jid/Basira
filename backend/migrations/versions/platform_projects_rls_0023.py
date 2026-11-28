"""Scope project rows to their owner with row level security.

The project record tables are already restricted by `personal_project_access` (platform_personal_0012),
but that policy is a subquery over `projects` and `projects` itself carried no policy at all: the
application role held plain SELECT on it, so a session bound to one owner could read every project row
of every account. This migration puts the same rule on the table the records hang from.

The policy stays permissive because it is the only policy on `projects`; a restrictive one would deny
every row. Row level security is enabled but not forced, because the deploy role owns the table and
`basira_project_owner` runs as its definer: an owner subject to RLS makes the function's
`row_security = off` raise instead of returning the owner for a queued job. The application role is
never the table owner, so it is filtered as intended.
"""

from alembic import op

revision = "platform_projects_rls_0023"
down_revision = "platform_owner_lookup_0022"
branch_labels = None
depends_on = None

# Archived projects must stay readable to their owner (list of deleted projects, restore), so the
# policy keys on ownership only; the application queries keep filtering `deleted_at`.
ALLOWED = """current_setting('basira.legacy_project_access', true) = '1'
    OR owner_user_id = current_setting('basira.owner_user_id', true)"""


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE projects ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY personal_project_access ON projects "
               f"USING ({ALLOWED}) WITH CHECK ({ALLOWED})")


def downgrade():
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP POLICY personal_project_access ON projects")
        op.execute("ALTER TABLE projects DISABLE ROW LEVEL SECURITY")
