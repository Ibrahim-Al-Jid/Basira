"""Store a scoped, redacted analyzer checkpoint until a scan reaches a terminal state."""

from alembic import op
import sqlalchemy as sa

revision = "platform_checkpoints_0015"
down_revision = "platform_personal_github_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("project_scans", sa.Column("analysis_checkpoint", sa.JSON(none_as_null=True)))
    if op.get_context().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION public.marsad_clear_analysis_checkpoint() RETURNS trigger
            LANGUAGE plpgsql SET search_path = pg_catalog AS $cleanup$
            BEGIN
                IF NEW.raw IS NULL OR NEW.state IN ('completed', 'partial', 'failed', 'cancelled') THEN
                    NEW.analysis_checkpoint := NULL;
                END IF;
                RETURN NEW;
            END;
            $cleanup$
        """)
        op.execute("""
            CREATE TRIGGER marsad_clear_analysis_checkpoint
            BEFORE UPDATE OF state, raw, analysis_checkpoint ON public.project_scans FOR EACH ROW
            EXECUTE FUNCTION public.marsad_clear_analysis_checkpoint()
        """)


def downgrade():
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP TRIGGER marsad_clear_analysis_checkpoint ON public.project_scans")
        op.execute("DROP FUNCTION public.marsad_clear_analysis_checkpoint()")
    op.drop_column("project_scans", "analysis_checkpoint")
