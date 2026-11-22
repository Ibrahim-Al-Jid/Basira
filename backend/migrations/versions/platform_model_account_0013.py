"""Allow the model gateway to resolve a personal credential for an active scan."""

from alembic import op

revision = "platform_model_account_0013"
down_revision = "platform_personal_0012"
branch_labels = None
depends_on = None

SIGNATURE = "public.marsad_start_account_model_call(text,text,text,text,text,text)"


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("""
        CREATE FUNCTION public.marsad_start_account_model_call(
            target_org text, target_project text, target_scan text, target_lease text,
            target_generation text, target_model text
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
              AND enrichment_reserved_at IS NOT NULL AND enrichment_started_at IS NULL
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
            UPDATE public.project_scans SET enrichment_started_at = (statement_timestamp() AT TIME ZONE 'UTC')
            WHERE id = target_scan AND org_id = target_org AND project_id = target_project;
            RETURN QUERY SELECT sealed, namespace_id;
        END;
        $start$;
    """)
    op.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'marsad_model_gateway') THEN
                GRANT EXECUTE ON FUNCTION {SIGNATURE} TO marsad_model_gateway;
            END IF;
        END $$;
    """)


def downgrade():
    if op.get_context().dialect.name == "postgresql":
        op.execute(f"DROP FUNCTION {SIGNATURE}")
