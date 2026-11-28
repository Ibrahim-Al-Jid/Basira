"""Purge expired authentication, throttle, invitation and GitHub rows.

Every table that carries an expiry date now has one owner for its cleanup. The dispatcher calls this
function on the same cadence as artifact expiry, so the rows cannot accumulate forever and the expiry
indexes are actually used.
"""

from alembic import op

revision = "platform_retention_0019"
down_revision = "platform_review_remap_0018"
branch_labels = None
depends_on = None

FUNCTION = "public.basira_purge_expired()"


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("""
        CREATE FUNCTION public.basira_purge_expired() RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog SET row_security = off
        AS $purge$
        DECLARE
            removed integer := 0;
            step integer;
        BEGIN
            DELETE FROM public.auth_sessions
            WHERE expires_at < (statement_timestamp() AT TIME ZONE 'UTC') - interval '1 day';
            GET DIAGNOSTICS step = ROW_COUNT;
            removed := removed + step;

            DELETE FROM public.password_attempt_limits
            WHERE "window" < (EXTRACT(EPOCH FROM statement_timestamp())::bigint - 86400);
            GET DIAGNOSTICS step = ROW_COUNT;
            removed := removed + step;

            DELETE FROM public.organization_invitations
            WHERE expires_at < (statement_timestamp() AT TIME ZONE 'UTC') - interval '30 days';
            GET DIAGNOSTICS step = ROW_COUNT;
            removed := removed + step;

            DELETE FROM public.personal_github_states
            WHERE expires_at < (statement_timestamp() AT TIME ZONE 'UTC') - interval '1 day';
            GET DIAGNOSTICS step = ROW_COUNT;
            removed := removed + step;

            DELETE FROM public.personal_github_grants
            WHERE expires_at < (statement_timestamp() AT TIME ZONE 'UTC') - interval '1 day';
            GET DIAGNOSTICS step = ROW_COUNT;
            removed := removed + step;

            RETURN removed;
        END;
        $purge$;
    """)
    op.execute(f"REVOKE ALL ON FUNCTION {FUNCTION} FROM PUBLIC")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_dispatch') THEN
                GRANT EXECUTE ON FUNCTION public.basira_purge_expired() TO basira_dispatch;
            END IF;
        END $$;
    """)


def downgrade():
    if op.get_context().dialect.name == "postgresql":
        op.execute(f"DROP FUNCTION {FUNCTION}")
