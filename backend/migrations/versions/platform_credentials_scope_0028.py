"""Scope password credentials, and make the attempt counter reachable only through a function.

`password_credentials` holds the one secret that makes an account takeover cheap, and it was readable by
any session. It is keyed by the account, so it takes the same policy shape as `auth_sessions`: a session
sees the row for the account it is acting as. The sign-in read already goes through
`basira_login_identity`, which runs as the definer, so nothing new is needed there.

`password_attempt_limits` is different: it is keyed by a hashed peer or email scope, and the reservation
happens before any account is known, so no owner-scoped policy can express it. The table becomes
definer-only: `basira_reserve_attempt` does the stale-window cleanup and the conditional upsert, and the
application loses direct access to the table.
"""

from alembic import op

revision = "platform_credentials_scope_0028"
down_revision = "platform_org_members_0027"
branch_labels = None
depends_on = None

FUNCTION = """
CREATE FUNCTION public.basira_reserve_attempt(scope_key text, window_start bigint, attempt_limit integer)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
SET row_security = off
AS $$
DECLARE
    counted integer;
BEGIN
    DELETE FROM public.password_attempt_limits WHERE "window" < window_start - 1;
    INSERT INTO public.password_attempt_limits (scope, "window", attempts)
    VALUES (scope_key, window_start, 1)
    ON CONFLICT (scope, "window") DO UPDATE
        SET attempts = public.password_attempt_limits.attempts + 1
        WHERE public.password_attempt_limits.attempts < attempt_limit
    RETURNING attempts INTO counted;
    RETURN counted;
END
$$
"""

SIGNATURE = "basira_reserve_attempt(text,bigint,integer)"


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute(FUNCTION)
    op.execute("ALTER TABLE password_credentials ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY personal_credential_access ON password_credentials
        USING (user_id = current_setting('basira.owner_user_id', true))
        WITH CHECK (user_id = current_setting('basira.owner_user_id', true))
    """)
    op.execute("ALTER TABLE password_attempt_limits ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON FUNCTION public.{SIGNATURE} FROM PUBLIC")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                GRANT EXECUTE ON FUNCTION public.basira_reserve_attempt(text, bigint, integer) TO basira_app;
                -- A password row is replaced or left alone, never deleted; the counter is definer-only.
                REVOKE DELETE ON password_credentials FROM basira_app;
                REVOKE SELECT, INSERT, UPDATE, DELETE ON password_attempt_limits FROM basira_app;
            END IF;
        END $$;
    """)


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                GRANT DELETE ON password_credentials TO basira_app;
                GRANT SELECT, INSERT, UPDATE, DELETE ON password_attempt_limits TO basira_app;
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE password_attempt_limits DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY personal_credential_access ON password_credentials")
    op.execute("ALTER TABLE password_credentials DISABLE ROW LEVEL SECURITY")
    op.execute(f"DROP FUNCTION public.{SIGNATURE}")
