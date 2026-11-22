"""Add isolated, expiring personal GitHub OAuth state and grants."""

from alembic import op
from sqlalchemy import text

from backend.platform_db import PersonalGitHubGrant, PersonalGitHubState

revision = "platform_personal_github_0014"
down_revision = "platform_model_account_0013"
branch_labels = None
depends_on = None


def upgrade():
    for model in (PersonalGitHubGrant, PersonalGitHubState):
        name = model.__tablename__
        model.__table__.create(op.get_bind())
        if op.get_context().dialect.name == "postgresql":
            op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
            op.execute(f"""CREATE POLICY personal_owner ON {name}
                        USING (user_id = current_setting('marsad.owner_user_id', true))
                        WITH CHECK (user_id = current_setting('marsad.owner_user_id', true))""")
            op.execute(text(f"""DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'marsad_app') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON {name} TO marsad_app;
                END IF;
            END $$"""))


def downgrade():
    for model in (PersonalGitHubState, PersonalGitHubGrant):
        op.drop_table(model.__tablename__)
