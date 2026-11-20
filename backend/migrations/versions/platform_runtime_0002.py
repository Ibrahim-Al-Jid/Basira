"""Add project scan jobs, transactional outbox, and scoped memory."""
from alembic import op
import sqlalchemy as sa

revision = "platform_runtime_0002"
down_revision = "platform_identity_0001"
branch_labels = None
depends_on = None

TENANT_NAMES = (
    "project_scans", "project_scan_events", "project_review_settings", "project_knowledge",
    "project_finding_observations", "project_legacy_reports",
)


def string(name, size=32, *, primary=False, nullable=False):
    return sa.Column(name, sa.String(size), primary_key=primary, nullable=nullable)


def organization(*, primary=False):
    return string("org_id", primary=primary)


def project(*, primary=False):
    return string("project_id", primary=primary)


def project_fk():
    return sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id"))


def scan_fk():
    return sa.ForeignKeyConstraint(("org_id", "project_id", "scan_id"),
                                   ("project_scans.org_id", "project_scans.project_id", "project_scans.id"),
                                   ondelete="CASCADE")


def upgrade():
    op.create_table(
        "project_scans", string("id", primary=True), organization(), project(), string("user_id"),
        string("idempotency_key", 100), string("request_digest", 64), string("state", 16),
        sa.Column("input_meta", sa.JSON, nullable=False), sa.Column("raw", sa.LargeBinary),
        sa.Column("policy", sa.JSON, nullable=False), sa.Column("report", sa.JSON),
        sa.Column("report_index", sa.JSON),
        sa.Column("attempt", sa.Integer, nullable=False), string("lease", nullable=True),
        sa.Column("lease_until", sa.DateTime), sa.Column("enrichment_reserved_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False), sa.Column("cursor", sa.Integer, nullable=False),
        project_fk(), sa.UniqueConstraint("org_id", "project_id", "id", name="uq_project_scans_scope"),
        sa.UniqueConstraint("org_id", "user_id", "idempotency_key", name="uq_project_scans_request"),
    )
    op.create_index("ix_project_scans_timeline", "project_scans", ["org_id", "project_id", "created_at"])
    op.create_table(
        "project_scan_events", organization(primary=True), project(primary=True), string("scan_id", primary=True),
        sa.Column("sequence", sa.Integer, primary_key=True), string("kind", 24), string("detail", 350),
        sa.Column("occurred_at", sa.DateTime, nullable=False), scan_fk(),
    )
    op.create_table(
        "scan_dispatch_outbox", string("scan_id", primary=True), organization(), project(),
        sa.Column("available_at", sa.DateTime, nullable=False), scan_fk(),
    )
    op.create_index("ix_scan_dispatch_outbox_available_at", "scan_dispatch_outbox", ["available_at"])
    op.create_table(
        "project_review_settings", organization(primary=True), project(primary=True),
        sa.Column("version", sa.Integer, nullable=False), sa.Column("policy", sa.JSON, nullable=False), project_fk(),
    )
    op.create_table(
        "project_knowledge", string("id", primary=True), organization(), project(),
        string("title", 160), string("reference", 500), string("note", 2000), string("reviewer_id"),
        sa.Column("created_at", sa.DateTime, nullable=False), sa.Column("revoked_at", sa.DateTime), project_fk(),
    )
    op.create_index("ix_project_knowledge_scope", "project_knowledge", ["org_id", "project_id", "created_at"])
    op.create_table(
        "project_finding_observations", organization(primary=True), project(primary=True),
        string("scan_id", primary=True), string("fingerprint", 64, primary=True), string("rule", 60),
        sa.Column("count", sa.Integer, nullable=False), scan_fk(),
    )
    op.create_index("ix_finding_fingerprint", "project_finding_observations", ["org_id", "project_id", "fingerprint"])
    op.create_table(
        "project_legacy_reports", string("legacy_id", primary=True), organization(), project(),
        string("user_id"), sa.Column("report", sa.JSON, nullable=False), sa.Column("report_index", sa.JSON, nullable=False),
        sa.Column("claimed_at", sa.DateTime, nullable=False), project_fk(),
    )
    op.create_index("ix_legacy_reports_scope", "project_legacy_reports", ["org_id", "project_id"])
    if op.get_context().dialect.name == "postgresql":
        clause = "org_id = current_setting('marsad.org_id', true) AND project_id = current_setting('marsad.project_id', true)"
        for name in TENANT_NAMES:
            op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY project_access ON {name} USING ({clause}) WITH CHECK ({clause})")
        op.execute("""
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'marsad_dispatch') THEN
                    GRANT SELECT, UPDATE ON scan_dispatch_outbox TO marsad_dispatch;
                END IF;
            END $$;
        """)


def downgrade():
    for name in reversed(TENANT_NAMES[2:]):
        op.drop_table(name)
    op.drop_table("scan_dispatch_outbox")
    op.drop_table("project_scan_events")
    op.drop_table("project_scans")
