"""Count the model calls a scan has made, and let the gateway spend them under a cap.

The Hunter's per-scan cap cannot be a read-then-write: two workers that both read `agent_calls = 4`
under a cap of 5 both decide they may call, and the scan makes six calls. A counter on the scan row
makes the check and the increment one statement,
`UPDATE project_scans SET agent_calls = agent_calls + 1 WHERE ... AND agent_calls < :cap RETURNING agent_calls`,
which the row lock serializes.

The column defaults to 0, so every scan that predates it reads as a scan that has made no model calls,
and a rules scan never touches it.

The gateway only ever calls SECURITY DEFINER functions in PostgreSQL, so the cap needs its own pair:
`basira_start_agent_call` and `basira_start_account_agent_call` are copies of
`basira_start_model_call` (platform_models_0008) and `basira_start_account_model_call`
(platform_model_account_0013) with the same membership, grant, connection and review-settings checks.
Two things differ: the scan must have a reserved enrichment slot and `agent_calls < call_cap`, and the
success path increments `agent_calls` and keeps `enrichment_started_at` at its first value, so a scan
can make several bounded calls while still recording when the model path opened.
"""

import sqlalchemy as sa
from alembic import op

revision = "platform_agent_calls_0033"
down_revision = "platform_login_identity_0032"
branch_labels = None
depends_on = None


AGENT_CALL = """
CREATE FUNCTION public.basira_start_agent_call(
    target_org text, target_project text, target_scan text, target_lease text,
    target_generation text, target_model text, call_cap integer
) RETURNS TABLE (ciphertext bytea)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog SET row_security = off
AS $start$
DECLARE
    actor text;
    sealed bytea;
    grant_id text;
BEGIN
    PERFORM id FROM public.projects WHERE id = target_project AND org_id = target_org FOR SHARE;
    IF NOT FOUND THEN RETURN; END IF;
    SELECT user_id INTO actor
    FROM public.project_scans
    WHERE id = target_scan AND org_id = target_org AND project_id = target_project
      AND state = 'running' AND lease = target_lease
      AND lease_until > (statement_timestamp() AT TIME ZONE 'UTC')
      AND source_expires_at > (statement_timestamp() AT TIME ZONE 'UTC')
      AND enrichment_reserved_at IS NOT NULL AND agent_calls < call_cap
      AND input_meta->>'connection_generation' = target_generation
      AND input_meta->>'connection_model' = target_model
    FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.memberships AS memberships
        JOIN public.users AS users ON users.id = actor
        WHERE memberships.org_id = target_org AND memberships.user_id = actor
          AND memberships.revoked_at IS NULL AND users.disabled_at IS NULL
          AND (memberships.role IN ('owner', 'admin') OR (
            memberships.role = 'analyst' AND EXISTS (
              SELECT 1 FROM public.project_grants
              WHERE org_id = target_org AND project_id = target_project
                AND user_id = actor AND revoked_at IS NULL
            )
          ))
    ) THEN RETURN; END IF;
    PERFORM id FROM public.organizations WHERE id = target_org FOR SHARE;
    SELECT model_connections.ciphertext, model_connections.grant_id INTO sealed, grant_id
    FROM public.organization_model_connections AS model_connections
    WHERE org_id = target_org;
    IF target_generation = 'operator' THEN
        IF FOUND THEN RETURN; END IF;
        grant_id := 'operator';
    ELSIF NOT FOUND OR NOT EXISTS (
        SELECT 1 FROM public.organization_model_connections
        WHERE org_id = target_org AND generation = target_generation AND model = target_model
    ) THEN RETURN;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.project_review_settings
        WHERE project_id = target_project AND org_id = target_org
          AND policy->>'model_connection' = 'openrouter-default'
          AND COALESCE(policy->>'model_grant_id', 'operator') = grant_id
    ) THEN RETURN; END IF;
    UPDATE public.project_scans
    SET agent_calls = agent_calls + 1,
        enrichment_started_at = COALESCE(enrichment_started_at,
                                         (statement_timestamp() AT TIME ZONE 'UTC'))
    WHERE id = target_scan AND org_id = target_org AND project_id = target_project;
    RETURN QUERY SELECT sealed;
END;
$start$;
"""

ACCOUNT_AGENT_CALL = """
CREATE FUNCTION public.basira_start_account_agent_call(
    target_org text, target_project text, target_scan text, target_lease text,
    target_generation text, target_model text, call_cap integer
) RETURNS TABLE (ciphertext bytea, credential_namespace text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog SET row_security = off
AS $start$
DECLARE
    actor text;
    namespace_id text;
    sealed bytea;
BEGIN
    SELECT project.owner_user_id INTO actor
    FROM public.projects AS project
    JOIN public.users AS owner ON owner.id = project.owner_user_id
    WHERE project.id = target_project AND project.org_id = target_org
      AND project.deleted_at IS NULL AND owner.disabled_at IS NULL
    FOR SHARE OF project, owner;
    IF NOT FOUND THEN RETURN; END IF;
    PERFORM id FROM public.project_scans
    WHERE id = target_scan AND org_id = target_org AND project_id = target_project AND user_id = actor
      AND state = 'running' AND lease = target_lease
      AND lease_until > (statement_timestamp() AT TIME ZONE 'UTC')
      AND source_expires_at > (statement_timestamp() AT TIME ZONE 'UTC')
      AND enrichment_reserved_at IS NOT NULL AND agent_calls < call_cap
      AND input_meta->>'connection_source' = 'account'
      AND input_meta->>'connection_generation' = target_generation
      AND input_meta->>'connection_model' = target_model
    FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    SELECT connection.ciphertext, namespace.id INTO sealed, namespace_id
    FROM public.organizations AS namespace
    JOIN public.organization_model_connections AS connection ON connection.org_id = namespace.id
    WHERE namespace.personal_owner_id = actor
      AND connection.generation = target_generation AND connection.model = target_model;
    IF NOT FOUND THEN RETURN; END IF;
    UPDATE public.project_scans
    SET agent_calls = agent_calls + 1,
        enrichment_started_at = COALESCE(enrichment_started_at,
                                         (statement_timestamp() AT TIME ZONE 'UTC'))
    WHERE id = target_scan AND org_id = target_org AND project_id = target_project;
    RETURN QUERY SELECT sealed, namespace_id;
END;
$start$;
"""

SIGNATURES = (
    "basira_start_agent_call(text,text,text,text,text,text,integer)",
    "basira_start_account_agent_call(text,text,text,text,text,text,integer)",
)


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.add_column(
        "project_scans",
        sa.Column("agent_calls", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_project_scans_agent_calls", "project_scans", "agent_calls >= 0"
    )
    op.execute(AGENT_CALL)
    op.execute(ACCOUNT_AGENT_CALL)
    for signature in SIGNATURES:
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_model_gateway') THEN
                GRANT EXECUTE ON FUNCTION public.basira_start_agent_call(
                    text, text, text, text, text, text, integer) TO basira_model_gateway;
                GRANT EXECUTE ON FUNCTION public.basira_start_account_agent_call(
                    text, text, text, text, text, text, integer) TO basira_model_gateway;
            END IF;
        END $$;
    """)


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    for signature in SIGNATURES:
        op.execute(f"DROP FUNCTION IF EXISTS public.{signature}")
    op.drop_constraint("ck_project_scans_agent_calls", "project_scans", type_="check")
    op.drop_column("project_scans", "agent_calls")
