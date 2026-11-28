"""Scope organizations and project grants to the people who may see them.

`organizations` carried no policy at all, so any session could read every organization name, every
personal namespace and the owner of each one. `project_grants` was the same: one session could read who
had been granted which project in every tenant.

The organization policy answers two questions that the application already asks: "the organizations I
belong to" (list_organizations, and the owner of a personal namespace) and "this one organization"
(everything that binds an organization before it asks). The membership subquery is safe because
`memberships` is already scoped, and it cannot recurse: the membership policy reads settings only.

`project_grants` is scoped the same way, with the legacy membership path kept open because the project
listing and the project access check read grants as part of a query that carries its own membership and
grant conditions (the same `basira.legacy_project_access` flag `projects` uses).

Both tables keep row level security enabled but not forced, for the reason recorded in
platform_projects_rls_0023: the deploy role owns them and the definer functions read with
`row_security = off`. Neither table is ever deleted from, so the application role loses DELETE on both.
"""

from alembic import op

revision = "platform_org_grants_0029"
down_revision = "platform_credentials_scope_0028"
branch_labels = None
depends_on = None

ORGANIZATIONS = """id = current_setting('basira.org_id', true)
    OR personal_owner_id = current_setting('basira.owner_user_id', true)
    OR EXISTS (
        SELECT 1 FROM public.memberships m
        WHERE m.org_id = organizations.id
          AND m.user_id = current_setting('basira.owner_user_id', true)
    )"""

ORGANIZATIONS_WRITE = """personal_owner_id IS NULL
    OR personal_owner_id = current_setting('basira.owner_user_id', true)"""

GRANTS = """org_id = current_setting('basira.org_id', true)
    OR user_id = current_setting('basira.owner_user_id', true)
    OR current_setting('basira.legacy_project_access', true) = '1'"""

GRANTS_WRITE = "org_id = current_setting('basira.org_id', true)"


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY organization_access ON organizations "
               f"USING ({ORGANIZATIONS}) WITH CHECK ({ORGANIZATIONS_WRITE})")
    op.execute("ALTER TABLE project_grants ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY project_grant_access ON project_grants "
               f"USING ({GRANTS}) WITH CHECK ({GRANTS_WRITE})")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                -- Organizations are closed by renaming their projects, never dropped; grants are revoked.
                REVOKE DELETE ON organizations FROM basira_app;
                REVOKE DELETE ON project_grants FROM basira_app;
            END IF;
        END $$;
    """)


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                GRANT DELETE ON organizations TO basira_app;
                GRANT DELETE ON project_grants TO basira_app;
            END IF;
        END $$;
    """)
    op.execute("DROP POLICY project_grant_access ON project_grants")
    op.execute("ALTER TABLE project_grants DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY organization_access ON organizations")
    op.execute("ALTER TABLE organizations DISABLE ROW LEVEL SECURITY")
