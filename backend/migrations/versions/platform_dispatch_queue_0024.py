"""Claim the dispatch queue through a definer function instead of a readable table.

`scan_dispatch_outbox` is the one queue the application role could read in full: it carried no policy,
so a session bound to one owner could see, delay or delete another account's pending dispatch. The
dispatcher needs a row nobody owns yet, so a policy keyed on the bound project cannot cover the claim
itself; a session flag set by the application would be spoofable by any SQL injection in the app. The
claim therefore moves into a SECURITY DEFINER function, the same pattern `basira_project_owner` uses,
and the table keeps a policy only for the two paths that already bind a project: the enqueue INSERT
and the DELETE in close_scan.

The claim function runs as the deploy role, which owns the table, so `row_security = off` is safe here
for the same reason as in `platform_project_owner`; the table stays unforced.
"""

from alembic import op

revision = "platform_dispatch_queue_0024"
down_revision = "platform_projects_rls_0023"
branch_labels = None
depends_on = None

ALLOWED = """org_id = current_setting('basira.org_id', true)
    AND project_id = current_setting('basira.project_id', true)"""

FUNCTIONS = (
    """
    CREATE FUNCTION public.basira_dispatch_claim(delay_seconds integer)
    RETURNS TABLE(scan_id text, org_id text, project_id text)
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog
    SET row_security = off
    AS $$
    DECLARE
        target record;
    BEGIN
        SELECT q.scan_id, q.org_id, q.project_id INTO target
        FROM public.scan_dispatch_outbox q
        WHERE q.available_at <= (statement_timestamp() AT TIME ZONE 'UTC')
        ORDER BY q.available_at
        LIMIT 1
        FOR UPDATE SKIP LOCKED;
        IF target.scan_id IS NULL THEN
            RETURN;
        END IF;
        UPDATE public.scan_dispatch_outbox q
        SET available_at = (statement_timestamp() AT TIME ZONE 'UTC')
            + make_interval(secs => delay_seconds)
        WHERE q.scan_id = target.scan_id;
        RETURN QUERY SELECT target.scan_id::text, target.org_id::text, target.project_id::text;
    END;
    $$
    """,
    """
    CREATE FUNCTION public.basira_dispatch_release(released text)
    RETURNS void
    LANGUAGE sql
    SECURITY DEFINER
    SET search_path = pg_catalog
    SET row_security = off
    AS $$
    UPDATE public.scan_dispatch_outbox
    SET available_at = (statement_timestamp() AT TIME ZONE 'UTC')
    WHERE scan_id = released
    $$
    """,
)

SIGNATURES = ("basira_dispatch_claim(integer)", "basira_dispatch_release(text)")


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    for statement in FUNCTIONS:
        op.execute(statement)
    op.execute("ALTER TABLE scan_dispatch_outbox ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY personal_project_access ON scan_dispatch_outbox "
               f"USING ({ALLOWED}) WITH CHECK ({ALLOWED})")
    for signature in SIGNATURES:
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                GRANT EXECUTE ON FUNCTION public.basira_dispatch_claim(integer) TO basira_app;
                GRANT EXECUTE ON FUNCTION public.basira_dispatch_release(text) TO basira_app;
                -- The claim and the reset go through the functions. SELECT stays because a DELETE
                -- whose WHERE reads scan_id needs it, and the policy scopes what it can see.
                REVOKE UPDATE ON scan_dispatch_outbox FROM basira_app;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_dispatch') THEN
                GRANT EXECUTE ON FUNCTION public.basira_dispatch_claim(integer) TO basira_dispatch;
                GRANT EXECUTE ON FUNCTION public.basira_dispatch_release(text) TO basira_dispatch;
                REVOKE SELECT, UPDATE ON scan_dispatch_outbox FROM basira_dispatch;
            END IF;
        END $$;
    """)


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                GRANT SELECT, UPDATE ON scan_dispatch_outbox TO basira_app;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_dispatch') THEN
                GRANT SELECT, UPDATE ON scan_dispatch_outbox TO basira_dispatch;
            END IF;
        END $$;
    """)
    op.execute("DROP POLICY personal_project_access ON scan_dispatch_outbox")
    op.execute("ALTER TABLE scan_dispatch_outbox DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION public.basira_dispatch_release(text)")
    op.execute("DROP FUNCTION public.basira_dispatch_claim(integer)")
