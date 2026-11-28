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
    "basira_login_identity(text,text)",
)


@pytest.fixture(scope="module")
def db():
    engine = sa.create_engine(URL)
    yield engine
    engine.dispose()


def scalar(db, statement, **values):
    with db.connect() as connection:
        return connection.execute(sa.text(statement), values).scalar_one()


def all_rows(db, statement, **values):
    """Every query closes its connection: the module shares one pool with the rest of the suite."""
    with db.connect() as connection:
        return connection.execute(sa.text(statement), values).all()


def one_row(db, statement, **values):
    with db.connect() as connection:
        return connection.execute(sa.text(statement), values).one()


def test_schema_is_at_head(db):
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    assert scalar(db, "SELECT version_num FROM alembic_version") == head


def test_tenant_tables_force_row_level_security(db):
    rows = all_rows(db,
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class AS c "
        "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = ANY(:names)",
        names=list(TENANT_TABLES))
    assert {row[0] for row in rows} == set(TENANT_TABLES)
    for name, enabled, forced in rows:
        assert enabled and forced, f"{name} must enable and force row level security"


def test_every_tenant_table_has_a_policy(db):
    rows = all_rows(db,
        "SELECT tablename, count(*) FROM pg_policies WHERE schemaname = 'public' "
        "AND tablename = ANY(:names) GROUP BY tablename", names=list(TENANT_TABLES))
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
    enabled, forced = one_row(db,
        "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class AS c "
        "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname = 'projects'")
    assert enabled, "projects must enable row level security"
    # Not forced on purpose: basira_project_owner reads projects as the deploy role's definer, and
    # row_security = off raises for an owner that is subject to RLS.
    assert not forced, "projects must stay unforced so the definer owner lookup keeps working"
    policies = all_rows(db,
        "SELECT policyname, permissive FROM pg_policies "
        "WHERE schemaname = 'public' AND tablename = 'projects'")
    assert ("personal_project_access", "PERMISSIVE") in policies


def test_dispatch_queue_is_claimed_through_a_definer_function(db):
    """The queue holds no payload, but the app role must not be able to read another tenant's rows."""
    enabled, _ = one_row(db,
        "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class AS c "
        "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname = 'scan_dispatch_outbox'")
    assert enabled, "scan_dispatch_outbox must enable row level security"
    policies = all_rows(db,
        "SELECT policyname, permissive FROM pg_policies "
        "WHERE schemaname = 'public' AND tablename = 'scan_dispatch_outbox'")
    assert ("personal_project_access", "PERMISSIVE") in policies
    with db.connect() as connection:
        if not connection.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'basira_app'")).first():
            pytest.skip("basira_app role is not provisioned")
        granted = connection.execute(sa.text(
            "SELECT has_table_privilege('basira_app', 'scan_dispatch_outbox', 'SELECT'), "
            "has_table_privilege('basira_app', 'scan_dispatch_outbox', 'UPDATE'), "
            "has_table_privilege('basira_app', 'scan_dispatch_outbox', 'INSERT'), "
            "has_table_privilege('basira_app', 'scan_dispatch_outbox', 'DELETE')")).one()
        # SELECT stays for the DELETE that reads scan_id; the policy scopes the rows it can see.
        assert granted == (True, False, True, True), "the queue is claimed through the function only"
        for signature in ("basira_dispatch_claim(integer)", "basira_dispatch_release(text)"):
            assert connection.execute(sa.text(
                "SELECT has_function_privilege('basira_app', CAST(:signature AS regprocedure), 'EXECUTE')"),
                {"signature": "public." + signature}).scalar_one()


def test_sessions_are_resolved_through_definer_functions(db):
    """The session lookup happens before any owner is known, so the table must not be readable."""
    enabled, _ = one_row(db,
        "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class AS c "
        "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname = 'auth_sessions'")
    assert enabled, "auth_sessions must enable row level security"
    policies = all_rows(db,
        "SELECT policyname, permissive FROM pg_policies "
        "WHERE schemaname = 'public' AND tablename = 'auth_sessions'")
    assert ("personal_session_access", "PERMISSIVE") in policies
    with db.connect() as connection:
        if not connection.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'basira_app'")).first():
            pytest.skip("basira_app role is not provisioned")
        granted = connection.execute(sa.text(
            "SELECT has_table_privilege('basira_app', 'auth_sessions', 'SELECT'), "
            "has_table_privilege('basira_app', 'auth_sessions', 'UPDATE'), "
            "has_table_privilege('basira_app', 'auth_sessions', 'DELETE'), "
            "has_table_privilege('basira_app', 'auth_sessions', 'INSERT')")).one()
        assert granted == (False, False, False, True), "sign-in inserts; lookup and revoke go through functions"
        for signature in ("basira_session_owner(text)", "basira_revoke_session(text)"):
            assert connection.execute(sa.text(
                "SELECT has_function_privilege('basira_app', CAST(:signature AS regprocedure), 'EXECUTE')"),
                {"signature": "public." + signature}).scalar_one()
            assert not connection.execute(sa.text(
                "SELECT has_function_privilege('public', CAST(:signature AS regprocedure), 'EXECUTE')"),
                {"signature": "public." + signature}).scalar_one()


def test_invitations_are_scoped_to_their_organization(db):
    """An invitation token is a credential: no session may read another organization's rows."""
    enabled, _ = one_row(db,
        "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class AS c "
        "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname = 'organization_invitations'")
    assert enabled, "organization_invitations must enable row level security"
    policies = all_rows(db,
        "SELECT policyname, permissive FROM pg_policies "
        "WHERE schemaname = 'public' AND tablename = 'organization_invitations'")
    assert ("organization_invitation_access", "PERMISSIVE") in policies
    with db.connect() as connection:
        if not connection.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'basira_app'")).first():
            pytest.skip("basira_app role is not provisioned")
        granted = connection.execute(sa.text(
            "SELECT has_table_privilege('basira_app', 'organization_invitations', 'SELECT'), "
            "has_table_privilege('basira_app', 'organization_invitations', 'INSERT'), "
            "has_table_privilege('basira_app', 'organization_invitations', 'UPDATE'), "
            "has_table_privilege('basira_app', 'organization_invitations', 'DELETE')")).one()
        assert granted == (True, True, True, False), "invitations are closed, never deleted"
        assert connection.execute(sa.text(
            "SELECT has_function_privilege('basira_app', "
            "CAST(:signature AS regprocedure), 'EXECUTE')"),
            {"signature": "public.basira_invitation_org(text)"}).scalar_one()
        assert not connection.execute(sa.text(
            "SELECT has_function_privilege('public', "
            "CAST(:signature AS regprocedure), 'EXECUTE')"),
            {"signature": "public.basira_invitation_org(text)"}).scalar_one()


def test_people_are_scoped_to_their_organization(db):
    """Accounts and memberships answer "me, plus the people in this organization", never the whole table."""
    with db.connect() as connection:
        for table, policy in (("users", "organization_people_access"),
                              ("memberships", "organization_membership_access")):
            enabled, _ = connection.execute(sa.text(
                "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class AS c "
                "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = :table"), {"table": table}).one()
            assert enabled, f"{table} must enable row level security"
            policies = connection.execute(sa.text(
                "SELECT policyname, permissive FROM pg_policies "
                "WHERE schemaname = 'public' AND tablename = :table"), {"table": table}).all()
            assert (policy, "PERMISSIVE") in policies, f"{table} needs the {policy} policy"
        if not connection.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'basira_app'")).first():
            pytest.skip("basira_app role is not provisioned")
        granted = connection.execute(sa.text(
            "SELECT has_table_privilege('basira_app', 'users', 'SELECT'), "
            "has_table_privilege('basira_app', 'users', 'INSERT'), "
            "has_table_privilege('basira_app', 'users', 'UPDATE'), "
            "has_table_privilege('basira_app', 'users', 'DELETE'), "
            "has_table_privilege('basira_app', 'memberships', 'SELECT'), "
            "has_table_privilege('basira_app', 'memberships', 'INSERT'), "
            "has_table_privilege('basira_app', 'memberships', 'UPDATE'), "
            "has_table_privilege('basira_app', 'memberships', 'DELETE')")).one()
        assert granted == (True, True, True, False, True, True, True, False), (
            "accounts and memberships are deactivated, never deleted")
        # Sign-in reads the account before a session exists, so it goes through the definer function.
        assert connection.execute(sa.text(
            "SELECT has_function_privilege('basira_app', "
            "CAST(:signature AS regprocedure), 'EXECUTE')"),
            {"signature": "public.basira_login_identity(text,text)"}).scalar_one()


def test_checkpoint_trigger_exists(db):
    assert scalar(db, "SELECT count(*) FROM pg_trigger WHERE tgname = 'basira_clear_analysis_checkpoint'") == 1


def test_idempotency_key_is_scoped_to_one_project(db):
    columns = [row[0] for row in all_rows(db,
        "SELECT a.attname FROM pg_index AS i "
        "JOIN pg_class AS c ON c.oid = i.indrelid "
        "JOIN pg_attribute AS a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey) "
        "WHERE c.relname = 'project_scans' AND i.indisunique "
        "AND i.indexrelid = CAST(:name AS regclass)", name="uq_project_scans_project_request")]
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


def test_credentials_are_scoped_and_attempts_are_definer_only(db):
    """A password hash belongs to one account; the attempt counter belongs to no account at all."""
    with db.connect() as connection:
        enabled, _ = connection.execute(sa.text(
            "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class AS c "
            "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'password_credentials'")).one()
        assert enabled, "password_credentials must enable row level security"
        policies = connection.execute(sa.text(
            "SELECT policyname, permissive FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = 'password_credentials'")).all()
        assert ("personal_credential_access", "PERMISSIVE") in policies
        attempts_enabled, _ = connection.execute(sa.text(
            "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class AS c "
            "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'password_attempt_limits'")).one()
        assert attempts_enabled, "password_attempt_limits must enable row level security"
        attempts_policies = connection.execute(sa.text(
            "SELECT policyname FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = 'password_attempt_limits'")).all()
        assert attempts_policies == [], "the counter is definer-only and needs no policy"
        if not connection.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'basira_app'")).first():
            pytest.skip("basira_app role is not provisioned")
        credential_grants = connection.execute(sa.text(
            "SELECT has_table_privilege('basira_app', 'password_credentials', 'SELECT'), "
            "has_table_privilege('basira_app', 'password_credentials', 'INSERT'), "
            "has_table_privilege('basira_app', 'password_credentials', 'UPDATE'), "
            "has_table_privilege('basira_app', 'password_credentials', 'DELETE')")).one()
        assert credential_grants == (True, True, True, False), "a password row is replaced, never deleted"
        assert connection.execute(sa.text(
            "SELECT has_table_privilege('basira_app', 'password_attempt_limits', :privilege)"),
            {"privilege": "SELECT"}).scalar_one() is False
        assert connection.execute(sa.text(
            "SELECT has_function_privilege('basira_app', "
            "CAST(:signature AS regprocedure), 'EXECUTE')"),
            {"signature": "public.basira_reserve_attempt(text,bigint,integer)"}).scalar_one()
        assert not connection.execute(sa.text(
            "SELECT has_function_privilege('public', "
            "CAST(:signature AS regprocedure), 'EXECUTE')"),
            {"signature": "public.basira_reserve_attempt(text,bigint,integer)"}).scalar_one()


def test_organizations_and_grants_are_scoped(db):
    """An organization name and a project grant both name people: neither may be read across tenants."""
    with db.connect() as connection:
        for table, policy in (("organizations", "organization_access"),
                              ("project_grants", "project_grant_access")):
            enabled, _ = connection.execute(sa.text(
                "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class AS c "
                "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = :table"), {"table": table}).one()
            assert enabled, f"{table} must enable row level security"
            policies = connection.execute(sa.text(
                "SELECT policyname, permissive FROM pg_policies "
                "WHERE schemaname = 'public' AND tablename = :table"), {"table": table}).all()
            assert (policy, "PERMISSIVE") in policies, f"{table} needs the {policy} policy"
        if not connection.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'basira_app'")).first():
            pytest.skip("basira_app role is not provisioned")
        granted = connection.execute(sa.text(
            "SELECT has_table_privilege('basira_app', 'organizations', 'SELECT'), "
            "has_table_privilege('basira_app', 'organizations', 'INSERT'), "
            "has_table_privilege('basira_app', 'organizations', 'UPDATE'), "
            "has_table_privilege('basira_app', 'organizations', 'DELETE'), "
            "has_table_privilege('basira_app', 'project_grants', 'SELECT'), "
            "has_table_privilege('basira_app', 'project_grants', 'INSERT'), "
            "has_table_privilege('basira_app', 'project_grants', 'UPDATE'), "
            "has_table_privilege('basira_app', 'project_grants', 'DELETE')")).one()
        assert granted == (True, True, True, False, True, True, True, False), (
            "organizations are never dropped and grants are revoked, never deleted")


def test_no_connection_is_left_checked_out(db):
    """A leaked connection here exhausts the pool the rest of the suite shares."""
    assert db.pool.checkedout() == 0
