"""Platform identity schema and scoped database transactions."""

from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
import os
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, LargeBinary, String,
    UniqueConstraint, create_engine, event, func, select, text,
)
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class PlatformUnavailable(RuntimeError):
    """The optional project platform has no configured database."""


def new_id():
    return uuid4().hex


def utc_now():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
        Index("ux_users_username", "username", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    issuer: Mapped[str] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(200))
    first_name: Mapped[str | None] = mapped_column(String(80))
    last_name: Mapped[str | None] = mapped_column(String(80))
    username: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="ck_auth_sessions_expiry"),
        Index("ix_auth_sessions_user", "user_id"),
        Index("ix_auth_sessions_expiry", "expires_at"),
    )

    token_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (Index("ux_organizations_personal_owner", "personal_owner_id", unique=True),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    personal_owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("role in ('owner', 'admin', 'analyst', 'viewer')", name="ck_memberships_role"),
        Index("ix_memberships_user", "user_id"),
    )

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(12))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_projects_org_id"),
        Index("ix_projects_org", "org_id"),
        Index("ix_projects_owner_active", "owner_user_id", "deleted_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GitHubConnection(Base):
    __tablename__ = "github_connections"
    __table_args__ = (
        CheckConstraint("status IN ('verified', 'revoked')", name="ck_github_connections_status"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    installation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    provider_account_id: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(12))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PersonalGitHubGrant(Base):
    __tablename__ = "personal_github_grants"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    provider_user_id: Mapped[str] = mapped_column(String(32))
    generation: Mapped[str] = mapped_column(String(32))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PersonalGitHubState(Base):
    __tablename__ = "personal_github_states"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    state_digest: Mapped[str] = mapped_column(String(64))
    session_digest: Mapped[str] = mapped_column(String(64))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProjectOwnershipReview(Base):
    """A project held back from the personal workspace until an administrator records a decision."""

    __tablename__ = "project_ownership_reviews"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    reason: Mapped[str] = mapped_column(String(32))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_ref: Mapped[str | None] = mapped_column(String(160))


class ProjectGrant(Base):
    __tablename__ = "project_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "project_id"], ["projects.org_id", "projects.id"],
            name="fk_project_grants_project",
        ),
        ForeignKeyConstraint(
            ["org_id", "user_id"], ["memberships.org_id", "memberships.user_id"],
            name="fk_project_grants_membership",
        ),
        Index("ix_project_grants_membership", "org_id", "user_id"),
    )

    org_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@lru_cache(maxsize=4)
def database_engine(url):
    sqlite = make_url(url).get_backend_name() == "sqlite"
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True,
                           connect_args={"autocommit": False} if sqlite else {})
    if sqlite:
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record):
            previous = connection.autocommit
            connection.autocommit = True
            try:
                connection.execute("PRAGMA foreign_keys=ON")
            finally:
                connection.autocommit = previous
    return engine


def platform_database_url():
    url = os.environ.get("BASIRA_PLATFORM_DATABASE_URL")
    if not url:
        raise PlatformUnavailable("Platform database is not configured.")
    return url


@contextmanager
def platform_session():
    """Open a single transaction. Use tenant_session for scoped project records."""
    with Session(database_engine(platform_database_url()), expire_on_commit=False) as db, db.begin():
        yield db


def personal_projects_enabled():
    return os.environ.get("BASIRA_PERSONAL_PROJECTS") == "1"


def personal_namespace_id(db, user_id, *, create=False):
    if create and not db.scalar(select(User.id).where(
        User.id == user_id, User.disabled_at.is_(None),
    ).with_for_update()):
        return None
    namespace = db.scalar(select(Organization.id).where(Organization.personal_owner_id == user_id))
    if namespace is None and create:
        organization = Organization(name="Personal projects", personal_owner_id=user_id)
        db.add(organization)
        db.flush()
        namespace = organization.id
        db.add(Membership(org_id=namespace, user_id=user_id, role="owner"))
    return namespace


def bind_owner(db, user_id):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT set_config('basira.owner_user_id', :owner, true)"), {"owner": user_id})


def bind_legacy_project_access(db):
    """Open the membership-scoped path: those queries carry their own membership and grant checks."""
    if personal_projects_enabled():
        return
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT set_config('basira.legacy_project_access', '1', true)"))


def bind_project(db, org_id, project_id, *, owner_user_id=None):
    """Bind trusted IDs for the current transaction; resetting happens on commit/rollback."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT set_config('basira.org_id', :org_id, true), "
                        "set_config('basira.project_id', :project_id, true), "
                        "set_config('basira.owner_user_id', :owner, true), "
                        "set_config('basira.legacy_project_access', :legacy, true)"),
                   {"org_id": org_id, "project_id": project_id, "owner": owner_user_id or "",
                    "legacy": "0" if personal_projects_enabled() else "1"})


def bind_project_context(db, context):
    bind_project(db, context.org_id, context.project_id, owner_user_id=context.owner_user_id)


def bind_job_project(db, org_id, project_id, *, lock=False):
    # The queue contains IDs only, so ownership comes from the project row. On PostgreSQL that read
    # happens before any owner is bound, which means it cannot go through row level security: the
    # definer function `basira_project_owner` resolves it, and only then is the context bound.
    if db.get_bind().dialect.name == "postgresql":
        row = db.execute(text("SELECT owner_user_id FROM public.basira_project_owner(:org_id, :project_id)"),
                         {"org_id": org_id, "project_id": project_id}).first()
        if row is None:
            return None
        if personal_projects_enabled() and not row[0]:
            return None
        bind_project(db, org_id, project_id, owner_user_id=row[0])
        return db.get(Project, project_id, with_for_update=lock) if lock else db.get(Project, project_id)
    project = db.get(Project, project_id, with_for_update=lock)
    if not project or project.org_id != org_id or project.deleted_at is not None:
        return None
    if personal_projects_enabled() and not project.owner_user_id:
        return None
    bind_project(db, org_id, project_id, owner_user_id=project.owner_user_id)
    return project


@contextmanager
def tenant_session(context):
    with platform_session() as db:
        bind_project_context(db, context)
        yield db
