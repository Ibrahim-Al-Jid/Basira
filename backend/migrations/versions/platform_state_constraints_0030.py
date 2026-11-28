"""Keep a scan in a state the application understands.

`project_scans.state` decides everything downstream: which scans the dispatcher claims, which the
retention sweep expires, which report the API serves, and when a scan is terminal. Nothing in the
database constrains it, so a typo or a half-finished write stores a value no query matches. The row
stays, disappears from every state-filtered read, and is never dispatched or expired again.

`finding_review_activity.status` records status changes for the review log. It carries the same four
values as `finding_reviews.status`, which has been constrained since platform_review_0003; the log
itself accepted anything.

Both constraints are added NOT VALID: new and updated rows are checked from now on, while the existing
rows are not scanned, so a value left over from before this migration cannot fail a deploy. Validate
them with ALTER TABLE ... VALIDATE CONSTRAINT once the stored data is known to be clean.
"""

from alembic import op

revision = "platform_state_constraints_0030"
down_revision = "platform_org_grants_0029"
branch_labels = None
depends_on = None

SCAN_STATES = "('queued', 'running', 'completed', 'partial', 'failed', 'cancelled')"
REVIEW_STATUSES = "('open', 'triaged', 'resolved', 'accepted')"


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE project_scans ADD CONSTRAINT ck_project_scans_state "
        "CHECK (state IN " + SCAN_STATES + ") NOT VALID"
    )
    op.execute(
        "ALTER TABLE finding_review_activity ADD CONSTRAINT ck_finding_review_activity_status "
        "CHECK (status IN " + REVIEW_STATUSES + ") NOT VALID"
    )


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE project_scans DROP CONSTRAINT IF EXISTS ck_project_scans_state")
    op.execute(
        "ALTER TABLE finding_review_activity "
        "DROP CONSTRAINT IF EXISTS ck_finding_review_activity_status"
    )
