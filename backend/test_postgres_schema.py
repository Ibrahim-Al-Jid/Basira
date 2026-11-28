"""Guards for the PostgreSQL schema that the SQLite fixtures cannot see.

Skipped unless `BASIRA_PLATFORM_MIGRATION_URL` points at a database that has already been migrated to
head, which is what the CI database job does before running the suite.
"""

import os

import pytest
import sqlalchemy as sa

URL = os.environ.get("BASIRA_PLATFORM_MIGRATION_URL")

pytestmark = pytest.mark.skipif(not URL, reason="needs a migrated PostgreSQL database")

TENANT_TABLES = (
    "project_scans", "project_scan_events", "project_review_settings", "project_knowledge",
    "project_finding_observations", "project_legacy_reports", "finding_reviews",
    "finding_review_activity", "project_assets", "project_scan_provenance",
    "project_evidence_records", "project_evidence_links", "project_github_sources",
)

FUNCTIONS = (
    "basira_expire_artifacts()", "basira_purge_expired()",
    "basira_model_credential(text,text)", "basira_start_model_call(text,text,text,text,text,text)",
    "basira_start_account_model_call(text,text,text,text,text,text)",
)


@pytest.fixture(scope="module")
def db():
    engine = sa.create_engine(URL)
    yield engine
    engine.dispose()


def scalar(db, statement, **values):
    with db.connect() as connection:
        return connection.execute(sa.text(statement), values).scalar_one()


def test_schema_is_at_head(db):
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    assert scalar(db, "SELECT version_num FROM alembic_version") == head


def test_tenant_tables_force_row_level_security(db):
    rows = db.connect().execute(sa.text(
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class AS c "
        "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = ANY(:names)"),
        {"names": list(TENANT_TABLES)}).all()
    assert {row[0] for row in rows} == set(TENANT_TABLES)
    for name, enabled, forced in rows:
        assert enabled and forced, f"{name} must enable and force row level security"


def test_every_tenant_table_has_a_policy(db):
    rows = db.connect().execute(sa.text(
        "SELECT tablename, count(*) FROM pg_policies WHERE schemaname = 'public' "
        "AND tablename = ANY(:names) GROUP BY tablename"), {"names": list(TENANT_TABLES)}).all()
    counts = {row[0]: row[1] for row in rows}
    for name in TENANT_TABLES:
        assert counts.get(name, 0) >= 1, f"{name} has no policy"


def test_security_definer_functions_are_not_public(db):
    for signature in FUNCTIONS:
        definer = scalar(db, "SELECT prosecdef FROM pg_proc WHERE oid = CAST(:signature AS regprocedure)",
                         signature=f"public.{signature}")
        assert definer, f"{signature} must be SECURITY DEFINER"
        granted = scalar(db, "SELECT has_function_privilege('public', CAST(:signature AS regprocedure), 'EXECUTE')",
                         signature=f"public.{signature}")
        assert not granted, f"{signature} must not be executable by PUBLIC"


def test_projects_table_is_owner_scoped(db):
    """The records are gated by a policy over `projects`, so the table itself must be gated too."""
    enabled, forced = db.connect().execute(sa.text(
        "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class AS c "
        "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname = 'projects'")).one()
    assert enabled, "projects must enable row level security"
    # Not forced on purpose: basira_project_owner reads projects as the deploy role's definer, and
    # row_security = off raises for an owner that is subject to RLS.
    assert not forced, "projects must stay unforced so the definer owner lookup keeps working"
    policies = db.connect().execute(sa.text(
        "SELECT policyname, permissive FROM pg_policies "
        "WHERE schemaname = 'public' AND tablename = 'projects'")).all()
    assert ("personal_project_access", "PERMISSIVE") in policies


def test_checkpoint_trigger_exists(db):
    assert scalar(db, "SELECT count(*) FROM pg_trigger WHERE tgname = 'basira_clear_analysis_checkpoint'") == 1


def test_idempotency_key_is_scoped_to_one_project(db):
    columns = db.connect().execute(sa.text(
        "SELECT a.attname FROM pg_index AS i "
        "JOIN pg_class AS c ON c.oid = i.indrelid "
        "JOIN pg_attribute AS a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey) "
        "WHERE c.relname = 'project_scans' AND i.indisunique "
        "AND i.indexrelid = CAST(:name AS regclass)"), {"name": "uq_project_scans_project_request"}).scalars().all()
    assert set(columns) == {"org_id", "project_id", "user_id", "idempotency_key"}


def test_app_role_cannot_write_immutable_evidence(db):
    with db.connect() as connection:
        roles = connection.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'basira_app'")).first()
        if not roles:
            pytest.skip("basira_app role is not provisioned")
        granted = connection.execute(sa.text(
            "SELECT has_table_privilege('basira_app', 'project_assets', 'UPDATE'), "
            "has_table_privilege('basira_app', 'project_assets', 'SELECT')")).one()
        assert granted == (False, True)


def test_app_role_has_no_access_to_the_ownership_queue_or_legacy_connections(db):
    """docs/ERD.md promises both tables are not visible to the application account."""
    with db.connect() as connection:
        if not connection.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'basira_app'")).first():
            pytest.skip("basira_app role is not provisioned")
        for table in ("project_ownership_reviews", "github_connections"):
            granted = connection.execute(sa.text(
                "SELECT has_table_privilege('basira_app', :table, 'SELECT'), "
                "has_table_privilege('basira_app', :table, 'INSERT'), "
                "has_table_privilege('basira_app', :table, 'UPDATE'), "
                "has_table_privilege('basira_app', :table, 'DELETE')"), {"table": table}).one()
            if table == "github_connections":
                # The app reads legacy connections through one endpoint; it must not write them.
                assert granted[0] is True, "basira_app must keep SELECT on github_connections"
                assert granted[1:] == (False, False, False), f"basira_app must not write {table}"
            else:
                assert granted == (False, False, False, False), f"basira_app must have no access to {table}"
