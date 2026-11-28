"""Resolve and revoke a session by token digest without an owner context.

`auth_sessions` is read on every authenticated request, and that read happens before any owner is
known: the token digest is the only input, so a policy keyed on the bound owner would hide the row the
request needs to find its own user. The lookup and the revoke therefore move into SECURITY DEFINER
functions, the pattern `basira_project_owner` and `basira_dispatch_claim` already use, and the table
keeps a policy for the one write the app makes once the user is known: the INSERT at sign-in.

`expires_at` is `timestamptz` and the application stores aware UTC instants, so the function compares
against `statement_timestamp()` directly.
"""

from alembic import op

revision = "platform_session_lookup_0025"
down_revision = "platform_dispatch_queue_0024"
branch_labels = None
depends_on = None

FUNCTIONS = (
    """
    CREATE FUNCTION public.basira_session_owner(digest text)
    RETURNS TABLE(user_id text)
    LANGUAGE sql
    SECURITY DEFINER
    SET search_path = pg_catalog
    SET row_security = off
    AS $$
    SELECT s.user_id::text
    FROM public.auth_sessions s
    WHERE s.token_digest = digest
      AND s.revoked_at IS NULL
      AND s.expires_at > statement_timestamp()
    $$
    """,
    """
    CREATE FUNCTION public.basira_revoke_session(digest text)
    RETURNS void
    LANGUAGE sql
    SECURITY DEFINER
    SET search_path = pg_catalog
    SET row_security = off
    AS $$
    UPDATE public.auth_sessions
    SET revoked_at = statement_timestamp()
    WHERE token_digest = digest
      AND revoked_at IS NULL
    $$
    """,
)

SIGNATURES = ("basira_session_owner(text)", "basira_revoke_session(text)")


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    for statement in FUNCTIONS:
        op.execute(statement)
    op.execute("ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY personal_session_access ON auth_sessions
        USING (user_id = current_setting('basira.owner_user_id', true))
        WITH CHECK (user_id = current_setting('basira.owner_user_id', true))
    """)
    for signature in SIGNATURES:
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                GRANT EXECUTE ON FUNCTION public.basira_session_owner(text) TO basira_app;
                GRANT EXECUTE ON FUNCTION public.basira_revoke_session(text) TO basira_app;
                -- Sign-in inserts the session; reading and revoking go through the functions.
                REVOKE SELECT, UPDATE, DELETE ON auth_sessions FROM basira_app;
            END IF;
        END $$;
    """)


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                GRANT SELECT, UPDATE, DELETE ON auth_sessions TO basira_app;
            END IF;
        END $$;
    """)
    op.execute("DROP POLICY personal_session_access ON auth_sessions")
    op.execute("ALTER TABLE auth_sessions DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION public.basira_revoke_session(text)")
    op.execute("DROP FUNCTION public.basira_session_owner(text)")
