"""Tables for the memory and audit trail of the hybrid agent system.

`docs/ARCHITECTURE-agents.md` section 5 splits memory into four kinds. Two of them are rows here:
project memory (`project_maps`, `project_candidate_verdicts`) and the audit trail of an agent scan
(`scan_agent_runs`, `scan_agent_steps`). Working memory is the existing checkpoint on `project_scans`,
and procedural memory is the rule catalog and tool registry, which carry no tenant data.

Every table is keyed by organization and project and carries the same two policies the project record
tables use, so a reader that has not bound the project sees nothing. The tables are defined here so the
migrations and the models agree; the read and write paths belong to the scan pipeline.
"""

import sqlalchemy as sa

from . import platform_runtime as store

metadata = store.metadata

project_maps = sa.Table(
    "project_maps", metadata,
    sa.Column("org_id", sa.String(32), primary_key=True),
    sa.Column("project_id", sa.String(32), primary_key=True),
    sa.Column("snapshot_digest", sa.String(64), primary_key=True),
    sa.Column("map", sa.JSON(none_as_null=True), nullable=False),
    sa.Column("builder", sa.String(40), nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id"),
                            name="project_maps_scope_fkey"),
    sa.Index("ix_project_maps_timeline", "org_id", "project_id", "created_at"),
    sa.Index("ix_project_maps_created_at", "created_at"),
)

candidate_verdicts = sa.Table(
    "project_candidate_verdicts", metadata,
    sa.Column("org_id", sa.String(32), primary_key=True),
    sa.Column("project_id", sa.String(32), primary_key=True),
    sa.Column("snapshot_digest", sa.String(64), primary_key=True),
    sa.Column("fingerprint", sa.String(64), primary_key=True),
    sa.Column("taxonomy_id", sa.String(40), nullable=False),
    sa.Column("status", sa.String(12), nullable=False),
    sa.Column("reason_code", sa.String(40), nullable=False),
    sa.Column("rule_id", sa.String(80)),
    sa.Column("checked_by", sa.String(80)),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id"),
                            name="project_candidate_verdicts_scope_fkey"),
    sa.CheckConstraint("status IN ('accepted', 'rejected', 'needs_human')",
                       name="ck_candidate_verdicts_status"),
    sa.Index("ix_candidate_verdicts_fingerprint", "org_id", "project_id", "fingerprint"),
    sa.Index("ix_candidate_verdicts_created_at", "created_at"),
)

agent_runs = sa.Table(
    "scan_agent_runs", metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("org_id", sa.String(32), nullable=False),
    sa.Column("project_id", sa.String(32), nullable=False),
    sa.Column("scan_id", sa.String(32), nullable=False),
    sa.Column("role_id", sa.String(24), nullable=False),
    sa.Column("analysis_mode", sa.String(16), nullable=False),
    sa.Column("model", sa.String(80)),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("budget_steps", sa.Integer, nullable=False),
    sa.Column("steps", sa.Integer, nullable=False),
    sa.Column("tokens_in", sa.Integer, nullable=False),
    sa.Column("tokens_out", sa.Integer, nullable=False),
    sa.Column("reason_code", sa.String(40)),
    sa.Column("started_at", sa.DateTime, nullable=False),
    sa.Column("ended_at", sa.DateTime),
    sa.ForeignKeyConstraint(("org_id", "project_id", "scan_id"),
                            ("project_scans.org_id", "project_scans.project_id", "project_scans.id"),
                            name="scan_agent_runs_scan_fkey"),
    sa.UniqueConstraint("org_id", "project_id", "scan_id", "id", name="uq_scan_agent_runs_scope"),
    sa.CheckConstraint(
        "role_id IN ('orchestrator', 'planning', 'analysis', 'validation', 'reporting')",
        name="ck_scan_agent_runs_role",
    ),
    sa.CheckConstraint("status IN ('running', 'completed', 'failed', 'over_budget', 'skipped')",
                       name="ck_scan_agent_runs_status"),
    sa.CheckConstraint("analysis_mode IN ('rules', 'agents', 'hybrid')",
                       name="ck_scan_agent_runs_mode"),
    sa.Index("ix_scan_agent_runs_scan", "org_id", "project_id", "scan_id"),
    sa.Index("ix_scan_agent_runs_started_at", "started_at"),
)

agent_steps = sa.Table(
    "scan_agent_steps", metadata,
    sa.Column("org_id", sa.String(32), primary_key=True),
    sa.Column("project_id", sa.String(32), primary_key=True),
    sa.Column("scan_id", sa.String(32), primary_key=True),
    sa.Column("run_id", sa.String(32), primary_key=True),
    sa.Column("sequence", sa.Integer, primary_key=True),
    sa.Column("tool_id", sa.String(40), nullable=False),
    sa.Column("tool_version", sa.String(40), nullable=False),
    sa.Column("outcome", sa.String(16), nullable=False),
    sa.Column("duration_ms", sa.Integer, nullable=False),
    sa.Column("result_bytes", sa.Integer, nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.ForeignKeyConstraint(
        ("org_id", "project_id", "scan_id", "run_id"),
        ("scan_agent_runs.org_id", "scan_agent_runs.project_id", "scan_agent_runs.scan_id",
         "scan_agent_runs.id"),
        name="scan_agent_steps_run_fkey", ondelete="CASCADE",
    ),
    sa.CheckConstraint("outcome IN ('ok', 'error', 'timeout', 'skipped')",
                       name="ck_scan_agent_steps_outcome"),
    sa.Index("ix_scan_agent_steps_created_at", "created_at"),
)
