"""Platform identity schema and scoped database transactions."""

from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
import os
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String,
    UniqueConstraint, create_engine, event, text,
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
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    issuer: Mapped[str] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(200))
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

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


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
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


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
    url = os.environ.get("MARSAD_PLATFORM_DATABASE_URL")
    if not url:
        raise PlatformUnavailable("Platform database is not configured.")
    return url


@contextmanager
def platform_session():
    """Open a single transaction. Use tenant_session for scoped project records."""
    with Session(database_engine(platform_database_url()), expire_on_commit=False) as db, db.begin():
        yield db


def bind_project(db, org_id, project_id):
    """Bind trusted IDs for the current transaction; resetting happens on commit/rollback."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT set_config('marsad.org_id', :org_id, true), "
                        "set_config('marsad.project_id', :project_id, true)"),
                   {"org_id": org_id, "project_id": project_id})


@contextmanager
def tenant_session(context):
    with platform_session() as db:
        bind_project(db, context.org_id, context.project_id)
        yield db
