"""Add project-scoped idempotency keys to project scans."""

from alembic import op

revision = "platform_idempotency_0017"
down_revision = "platform_providers_0016"
branch_labels = None
depends_on = None

OLD = "uq_project_scans_request"
NEW = "uq_project_scans_project_request"


def upgrade():
    # A key belongs to one project. The old constraint spanned the whole organization, so reusing the
    # same key in a second project of the same organization failed with a false conflict.
    op.drop_constraint(OLD, "project_scans", type_="unique")
    op.create_unique_constraint(NEW, "project_scans", ["org_id", "project_id", "user_id", "idempotency_key"])


def downgrade():
    op.drop_constraint(NEW, "project_scans", type_="unique")
    op.create_unique_constraint(OLD, "project_scans", ["org_id", "user_id", "idempotency_key"])
