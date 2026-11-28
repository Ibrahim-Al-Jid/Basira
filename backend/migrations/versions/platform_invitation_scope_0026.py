"""Scope invitations to the organization that owns them.

An invitation token is a credential: whoever reads the digest row can accept it. Until now any session
could read every organization's invitations, so the table was the shortest path from one tenant to
another. The accept path is the only read that happens before an organization is known (the token is
the input), so it moves into a SECURITY DEFINER function; the owner paths bind the organization and then
the policy covers the rest.
"""

from alembic import op

revision = "platform_invitation_scope_0026"
down_revision = "platform_session_lookup_0025"
branch_labels = None
depends_on = None

FUNCTION = """
CREATE FUNCTION public.basira_invitation_org(digest text)
RETURNS TABLE(org_id text)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog
SET row_security = off
AS $$
SELECT i.org_id::text
FROM public.organization_invitations i
WHERE i.token_digest = digest
  AND i.closed_at IS NULL
  AND i.expires_at > (statement_timestamp() AT TIME ZONE 'UTC')
$$
"""

SIGNATURE = "basira_invitation_org(text)"


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute(FUNCTION)
    op.execute("ALTER TABLE organization_invitations ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY organization_invitation_access ON organization_invitations
        USING (org_id = current_setting('basira.org_id', true))
        WITH CHECK (org_id = current_setting('basira.org_id', true))
    """)
    op.execute(f"REVOKE ALL ON FUNCTION public.{SIGNATURE} FROM PUBLIC")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                GRANT EXECUTE ON FUNCTION public.basira_invitation_org(text) TO basira_app;
                -- Listing, creating and closing an invitation all run with the organization bound.
                REVOKE DELETE ON organization_invitations FROM basira_app;
            END IF;
        END $$;
    """)


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                GRANT DELETE ON organization_invitations TO basira_app;
            END IF;
        END $$;
    """)
    op.execute("DROP POLICY organization_invitation_access ON organization_invitations")
    op.execute("ALTER TABLE organization_invitations DISABLE ROW LEVEL SECURITY")
    op.execute(f"DROP FUNCTION public.{SIGNATURE}")
