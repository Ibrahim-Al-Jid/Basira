"""Persist encrypted model credentials and install the gateway's restricted access."""
from alembic import op
import sqlalchemy as sa

revision = "platform_models_0008"
down_revision = "platform_invitations_0007"
branch_labels = None
depends_on = None

TABLES = ("organization_model_connections", "organization_model_attempts")


def scope_column():
    return sa.Column("org_id", sa.String(32),
                     sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)


def authorize_gateway():
    op.execute("""
        CREATE FUNCTION public.basira_model_credential(target_org text, target_generation text)
        RETURNS bytea LANGUAGE SQL SECURITY DEFINER SET search_path = pg_catalog SET row_security = off
        AS $credential$
            SELECT ciphertext FROM public.organization_model_connections
            WHERE org_id = target_org AND generation = target_generation;
        $credential$;
    """)
    op.execute("""
        CREATE FUNCTION public.basira_start_model_call(
            target_org text, target_project text, target_scan text, target_lease text,
            target_generation text, target_model text
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
              AND enrichment_reserved_at IS NOT NULL AND enrichment_started_at IS NULL
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
            UPDATE public.project_scans SET enrichment_started_at = (statement_timestamp() AT TIME ZONE 'UTC')
            WHERE id = target_scan AND org_id = target_org AND project_id = target_project;
            RETURN QUERY SELECT sealed;
        END;
        $start$;
    """)
    for signature in ("basira_model_credential(text,text)", "basira_start_model_call(text,text,text,text,text,text)"):
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
        op.execute(f"""
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_model_gateway') THEN
                    GRANT EXECUTE ON FUNCTION public.{signature} TO basira_model_gateway;
                END IF;
            END $$;
        """)


def upgrade():
    op.create_table(
        TABLES[0], scope_column(), sa.Column("generation", sa.String(32), nullable=False),
        sa.Column("grant_id", sa.String(32), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary, nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        TABLES[1], scope_column(), sa.Column("window", sa.BigInteger, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.CheckConstraint("attempts > 0", name="ck_organization_model_attempts_positive"),
    )
    op.add_column("project_scans", sa.Column("enrichment_started_at", sa.DateTime))
    if op.get_context().dialect.name == "postgresql":
        filter_ = "org_id = current_setting('basira.model_org_id', true)"
        for name in TABLES:
            op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY organization_access ON {name} USING ({filter_}) WITH CHECK ({filter_})")
        authorize_gateway()


def downgrade():
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP FUNCTION public.basira_start_model_call(text,text,text,text,text,text)")
        op.execute("DROP FUNCTION public.basira_model_credential(text,text)")
    op.drop_column("project_scans", "enrichment_started_at")
    for name in reversed(TABLES):
        op.drop_table(name)
