"""Resolve a project's owner without depending on the caller's row-level-security context.

`bind_job_project` runs on the dispatch path, where the queue carries only ids: the owner of the project
has to be read before any owner context exists, so an owner-keyed policy on `projects` would hide the row
from the dispatcher and stall every queued job. This revision adds a definer function that answers that
one question, and nothing else: the owner of a live project in a given organization. It is the same shape
as the other definer functions in this schema (`basira_expire_artifacts`, `basira_purge_expired`).
"""

from alembic import op

revision = "platform_owner_lookup_0022"
down_revision = "platform_user_foreign_keys_0020"
branch_labels = None
depends_on = None

FUNCTION = "public.basira_project_owner(text, text)"


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("""
        CREATE FUNCTION public.basira_project_owner(org_id text, project_id text)
        RETURNS TABLE (owner_user_id text)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog
        SET row_security = off
        AS $owner$
            SELECT p.owner_user_id
            FROM public.projects AS p
            WHERE p.id = project_id AND p.org_id = org_id AND p.deleted_at IS NULL
        $owner$;
    """)
    op.execute(f"REVOKE ALL ON FUNCTION {FUNCTION} FROM PUBLIC")
    op.execute("""
        DO $$
        DECLARE role_name text;
        BEGIN
            FOREACH role_name IN ARRAY ARRAY['basira_app', 'basira_dispatch'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
                    EXECUTE format('GRANT EXECUTE ON FUNCTION public.basira_project_owner(text, text) TO %I', role_name);
                END IF;
            END LOOP;
        END $$;
    """)


def downgrade():
    if op.get_context().dialect.name == "postgresql":
        op.execute(f"DROP FUNCTION {FUNCTION}")
