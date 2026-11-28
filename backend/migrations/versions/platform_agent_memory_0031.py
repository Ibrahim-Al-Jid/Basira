"""Store what the hybrid agent system has to remember, scoped like every other project row.

Four new tables, all keyed by organization and project, all carrying the same pair of policies the
project record tables use: a permissive `project_access` on the bound organization and project, and a
restrictive `personal_project_access` that keeps the owner path working. Row level security is enabled
and forced, as on `project_scans` and `project_scan_events`, so a query that forgets to bind reads
nothing instead of reading another tenant.

`project_maps` is the project memory of docs/ARCHITECTURE-agents.md section 5: one `ProjectMap` per
snapshot digest, so an unchanged snapshot is understood once and a changed one is understood again.

`project_candidate_verdicts` records what the validator decided about a candidate fingerprint for a
digest, with a fixed reason code. That is what stops the same false positive being proposed again for
an identical snapshot, and what keeps the accepted set reproducible without a model.

`scan_agent_runs` and `scan_agent_steps` are the run and step records of section 7a: one row per agent
role per scan with its budget, step count, tokens and reason code, and one row per tool call with its
version, duration and result size. `project_scans.analysis_mode` records which path the scan took
(`rules`, `agents` or `hybrid`); the column defaults to `rules`, so every scan that predates this
migration reads as a rules scan, and the setting layer supplies `hybrid` for new scans.

Retention: `basira_purge_expired` gains the four tables. Run and step records go after 90 days, the same
window the review context uses; maps and verdicts go after 180 days, because they are only useful while
a digest can still come back. The application role loses DELETE on all four: the purge is the only
deleter and it runs as its definer.
"""

import sqlalchemy as sa
from alembic import op

revision = "platform_agent_memory_0031"
down_revision = "platform_state_constraints_0030"
branch_labels = None
depends_on = None

PROJECT_ACCESS = """org_id = current_setting('basira.org_id', true)
    AND project_id = current_setting('basira.project_id', true)"""

PERSONAL_ACCESS = """EXISTS (
        SELECT 1 FROM public.projects p
        WHERE p.id = {table}.project_id
          AND p.org_id = {table}.org_id
          AND p.deleted_at IS NULL
          AND (current_setting('basira.legacy_project_access', true) = '1'
               OR p.owner_user_id = current_setting('basira.owner_user_id', true))
    )"""

AGENT_TABLES = (
    "project_maps",
    "project_candidate_verdicts",
    "scan_agent_runs",
    "scan_agent_steps",
)

PURGE = """
    CREATE OR REPLACE FUNCTION public.basira_purge_expired() RETURNS integer
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog
    SET row_security = off
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

        DELETE FROM public.scan_agent_steps
        WHERE created_at < (statement_timestamp() AT TIME ZONE 'UTC') - interval '90 days';
        GET DIAGNOSTICS step = ROW_COUNT;
        removed := removed + step;

        DELETE FROM public.scan_agent_runs
        WHERE started_at < (statement_timestamp() AT TIME ZONE 'UTC') - interval '90 days';
        GET DIAGNOSTICS step = ROW_COUNT;
        removed := removed + step;

        DELETE FROM public.project_maps
        WHERE created_at < (statement_timestamp() AT TIME ZONE 'UTC') - interval '180 days';
        GET DIAGNOSTICS step = ROW_COUNT;
        removed := removed + step;

        DELETE FROM public.project_candidate_verdicts
        WHERE created_at < (statement_timestamp() AT TIME ZONE 'UTC') - interval '180 days';
        GET DIAGNOSTICS step = ROW_COUNT;
        removed := removed + step;

        RETURN removed;
    END;
    $purge$
"""


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return

    op.add_column(
        "project_scans",
        sa.Column("analysis_mode", sa.String(16), nullable=False, server_default="rules"),
    )
    op.create_check_constraint(
        "ck_project_scans_analysis_mode",
        "project_scans",
        "analysis_mode IN ('rules', 'agents', 'hybrid')",
    )

    op.create_table(
        "project_maps",
        sa.Column("org_id", sa.String(32), nullable=False),
        sa.Column("project_id", sa.String(32), nullable=False),
        sa.Column("snapshot_digest", sa.String(64), nullable=False),
        sa.Column("map", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("builder", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "project_id", "snapshot_digest"),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"], ["projects.org_id", "projects.id"], name="project_maps_scope_fkey"
        ),
    )
    op.create_index("ix_project_maps_timeline", "project_maps", ["org_id", "project_id", "created_at"])
    op.create_index("ix_project_maps_created_at", "project_maps", ["created_at"])

    op.create_table(
        "project_candidate_verdicts",
        sa.Column("org_id", sa.String(32), nullable=False),
        sa.Column("project_id", sa.String(32), nullable=False),
        sa.Column("snapshot_digest", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("taxonomy_id", sa.String(40), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("rule_id", sa.String(80)),
        sa.Column("checked_by", sa.String(80)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "project_id", "snapshot_digest", "fingerprint"),
        sa.CheckConstraint(
            "status IN ('accepted', 'rejected', 'needs_human')", name="ck_candidate_verdicts_status"
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            name="project_candidate_verdicts_scope_fkey",
        ),
    )
    op.create_index(
        "ix_candidate_verdicts_fingerprint",
        "project_candidate_verdicts",
        ["org_id", "project_id", "fingerprint"],
    )
    op.create_index("ix_candidate_verdicts_created_at", "project_candidate_verdicts", ["created_at"])

    op.create_table(
        "scan_agent_runs",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("org_id", sa.String(32), nullable=False),
        sa.Column("project_id", sa.String(32), nullable=False),
        sa.Column("scan_id", sa.String(32), nullable=False),
        sa.Column("role_id", sa.String(24), nullable=False),
        sa.Column("analysis_mode", sa.String(16), nullable=False),
        sa.Column("model", sa.String(80)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("budget_steps", sa.Integer(), nullable=False),
        sa.Column("steps", sa.Integer(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(40)),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "project_id", "scan_id", "id", name="uq_scan_agent_runs_scope"),
        sa.CheckConstraint(
            "role_id IN ('orchestrator', 'planning', 'analysis', 'validation', 'reporting')",
            name="ck_scan_agent_runs_role",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'over_budget', 'skipped')",
            name="ck_scan_agent_runs_status",
        ),
        sa.CheckConstraint(
            "analysis_mode IN ('rules', 'agents', 'hybrid')", name="ck_scan_agent_runs_mode"
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id", "scan_id"],
            ["project_scans.org_id", "project_scans.project_id", "project_scans.id"],
            name="scan_agent_runs_scan_fkey",
        ),
    )
    op.create_index("ix_scan_agent_runs_scan", "scan_agent_runs", ["org_id", "project_id", "scan_id"])
    op.create_index("ix_scan_agent_runs_started_at", "scan_agent_runs", ["started_at"])

    op.create_table(
        "scan_agent_steps",
        sa.Column("org_id", sa.String(32), nullable=False),
        sa.Column("project_id", sa.String(32), nullable=False),
        sa.Column("scan_id", sa.String(32), nullable=False),
        sa.Column("run_id", sa.String(32), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("tool_id", sa.String(40), nullable=False),
        sa.Column("tool_version", sa.String(40), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("result_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "project_id", "scan_id", "run_id", "sequence"),
        sa.CheckConstraint(
            "outcome IN ('ok', 'error', 'timeout', 'skipped')", name="ck_scan_agent_steps_outcome"
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id", "scan_id", "run_id"],
            [
                "scan_agent_runs.org_id",
                "scan_agent_runs.project_id",
                "scan_agent_runs.scan_id",
                "scan_agent_runs.id",
            ],
            name="scan_agent_steps_run_fkey",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_scan_agent_steps_created_at", "scan_agent_steps", ["created_at"])

    for table in AGENT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY project_access ON {table} USING ({PROJECT_ACCESS}) "
            f"WITH CHECK ({PROJECT_ACCESS})"
        )
        personal = PERSONAL_ACCESS.format(table=table)
        op.execute(
            f"CREATE POLICY personal_project_access ON {table} AS RESTRICTIVE "
            f"USING ({personal}) WITH CHECK ({personal})"
        )

    op.execute(PURGE)
    op.execute("REVOKE ALL ON FUNCTION public.basira_purge_expired() FROM PUBLIC")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                REVOKE DELETE ON project_maps, project_candidate_verdicts, scan_agent_runs,
                    scan_agent_steps FROM basira_app;
                GRANT EXECUTE ON FUNCTION public.basira_purge_expired() TO basira_app;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_dispatch') THEN
                GRANT EXECUTE ON FUNCTION public.basira_purge_expired() TO basira_dispatch;
            END IF;
        END $$;
    """)


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app') THEN
                GRANT DELETE ON project_maps, project_candidate_verdicts, scan_agent_runs,
                    scan_agent_steps TO basira_app;
            END IF;
        END $$;
    """)
    for table in AGENT_TABLES:
        op.execute(f"DROP POLICY personal_project_access ON {table}")
        op.execute(f"DROP POLICY project_access ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("scan_agent_steps")
    op.drop_table("scan_agent_runs")
    op.drop_table("project_candidate_verdicts")
    op.drop_table("project_maps")
    op.drop_constraint("ck_project_scans_analysis_mode", "project_scans", type_="check")
    op.drop_column("project_scans", "analysis_mode")
