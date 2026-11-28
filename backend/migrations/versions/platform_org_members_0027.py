"""Scope users and memberships so one account cannot read another organization's people.

`users` and `memberships` are the pair that cannot be closed one at a time. A `users` policy has to
answer "myself, plus the people who share an organization with me", which it does by reading
`memberships`; if `memberships` were still unguarded, that subquery would be the way around the policy.
So both get a policy here, keyed on the owner that is already bound or the organization that a request
binds before it asks about people.

One read happens before either is known: sign-in looks a person up by issuer and subject. It moves into
`basira_login_identity`, which also returns the password hash the login already compares in process, so
the login path no longer reads `password_credentials` either.
"""

from alembic import op

revision = "platform_org_members_0027"
down_revision = "platform_invitation_scope_0026"
branch_labels = None
depends_on = None

FUNCTION = """
CREATE FUNCTION public.basira_login_identity(issuer text, subject text)
RETURNS TABLE(user_id text, disabled_at timestamp with time zone, password_hash text)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog
SET row_security = off
AS $$
SELECT u.id::text, u.disabled_at, c.password_hash::text
FROM public.users u
LEFT JOIN public.password_credentials c ON c.user_id = u.id
WHERE u.issuer = issuer
  AND u.subject = subject
$$
"""

SIGNATURE = "basira_login_identity(text,text)"


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute(FUNCTION)
    op.execute("ALTER TABLE memberships ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY organization_membership_access ON memberships
        USING (user_id = current_setting('basira.owner_user_id', true)
            OR org_id = current_setting('basira.org_id', true))
        WITH CHECK (user_id = current_setting('basira.owner_user_id', true)
            OR org_id = current_setting('basira.org_id', true))
    """)
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY organization_people_access ON users
        USING (id = current_setting('basira.owner_user_id', true) OR EXISTS (
            SELECT 1 FROM public.memberships m
            WHERE m.user_id = users.id
              AND m.org_id = current_setting('basira.org_id', true)
        ))
        WITH CHECK (id = current_setting('basira.owner_user_id', true))
    """)
    op.execute(f"REVOKE ALL ON FUNCTION public.{SIGNATURE} FROM PUBLIC")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                GRANT EXECUTE ON FUNCTION public.basira_login_identity(text, text) TO basira_app;
                -- Accounts and memberships are deactivated, never deleted, by the application.
                REVOKE DELETE ON users FROM basira_app;
                REVOKE DELETE ON memberships FROM basira_app;
            END IF;
        END $$;
    """)


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                GRANT DELETE ON users TO basira_app;
                GRANT DELETE ON memberships TO basira_app;
            END IF;
        END $$;
    """)
    op.execute("DROP POLICY organization_people_access ON users")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY organization_membership_access ON memberships")
    op.execute("ALTER TABLE memberships DISABLE ROW LEVEL SECURITY")
    op.execute(f"DROP FUNCTION public.{SIGNATURE}")
