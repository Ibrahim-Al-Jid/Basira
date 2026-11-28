"""Organization-scoped, single-use invitations shared privately by the owner."""
from datetime import datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, select, text
from sqlalchemy.orm import Mapped, mapped_column

from .identity import require_membership, require_user
from .platform_db import Base, Membership, Organization, bind_org, new_id, platform_session, utc_now

router = APIRouter(prefix="/api/platform", tags=["Organization invitations"])
INVITATION_TTL = timedelta(hours=24)
MAX_ACTIVE = 20
AssignableRole = Literal["admin", "analyst", "viewer"]


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        CheckConstraint("role in ('admin', 'analyst', 'viewer')", name="ck_organization_invitations_role"),
        Index("ix_organization_invitations_org_expiry", "org_id", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(12))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: AssignableRole


class AcceptInvitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


def active_invitations(org_id, now):
    return select(OrganizationInvitation).where(
        OrganizationInvitation.org_id == org_id,
        OrganizationInvitation.closed_at.is_(None),
        OrganizationInvitation.expires_at > now,
    )


def require_owner(db, org_id, user_id):
    if require_membership(db, org_id, user_id).role != "owner":
        raise HTTPException(403, "إدارة الدعوات متاحة لمالك المؤسسة.")


def lock_organization(db, org_id):
    return db.scalar(select(Organization).where(Organization.id == org_id).with_for_update())


def digest(token):
    return sha256(token.encode("ascii")).hexdigest()


def public_row(row):
    return {"id": row.id, "role": row.role, "expires_at": row.expires_at.isoformat()}


@router.get("/organizations/{org_id}/invitations")
def invitations(org_id: str, request: Request):
    user = require_user(request)
    with platform_session() as db:
        require_owner(db, org_id, user.id)
        bind_org(db, org_id)
        rows = db.scalars(active_invitations(org_id, utc_now()).order_by(OrganizationInvitation.expires_at))
        return {"invitations": [public_row(row) for row in rows]}


@router.post("/organizations/{org_id}/invitations", status_code=201)
def create_invitation(org_id: str, body: InvitationInput, request: Request):
    user = require_user(request)
    with platform_session() as db:
        require_owner(db, org_id, user.id)
        bind_org(db, org_id)
        lock_organization(db, org_id)
        now = utc_now()
        if len(db.scalars(active_invitations(org_id, now).limit(MAX_ACTIVE)).all()) >= MAX_ACTIVE:
            raise HTTPException(409, "تم الوصول للحد الأقصى من الدعوات النشطة.")
        token = token_urlsafe(32)
        row = OrganizationInvitation(org_id=org_id, role=body.role,
                                     token_digest=digest(token), expires_at=now + INVITATION_TTL)
        db.add(row)
        db.flush()
        return {**public_row(row), "token": token}


@router.delete("/organizations/{org_id}/invitations/{invitation_id}", status_code=204)
def revoke_invitation(org_id: str, invitation_id: str, request: Request):
    user = require_user(request)
    with platform_session() as db:
        require_owner(db, org_id, user.id)
        bind_org(db, org_id)
        lock_organization(db, org_id)
        now = utc_now()
        row = db.scalar(active_invitations(org_id, now).where(OrganizationInvitation.id == invitation_id))
        if not row:
            raise HTTPException(404, "الدعوة غير متاحة.")
        row.closed_at = now


@router.post("/invitations/accept")
def accept_invitation(body: AcceptInvitation, request: Request):
    user = require_user(request)
    with platform_session() as db:
        token_digest = digest(body.token)
        # The token is the only input here, so the organization is resolved outside row level
        # security; everything after that runs with the organization bound.
        if db.get_bind().dialect.name == "postgresql":
            org_id = db.scalar(text("SELECT org_id FROM public.basira_invitation_org(:digest)"),
                               {"digest": token_digest})
        else:
            org_id = db.scalar(select(OrganizationInvitation.org_id).where(
                OrganizationInvitation.token_digest == token_digest,
                OrganizationInvitation.closed_at.is_(None),
                OrganizationInvitation.expires_at > utc_now(),
            ))
        if not org_id:
            raise HTTPException(404, "الدعوة غير متاحة.")
        bind_org(db, org_id)
        org = lock_organization(db, org_id)
        now = utc_now()
        row = db.scalar(active_invitations(org_id, now).where(
            OrganizationInvitation.token_digest == token_digest))
        if not org or not row:
            raise HTTPException(404, "الدعوة غير متاحة.")
        member = db.get(Membership, (org_id, user.id))
        if member and member.revoked_at is None:
            raise HTTPException(409, "أنت عضو في المؤسسة بالفعل.")
        if member:
            member.role, member.revoked_at, member.joined_at = row.role, None, now
        else:
            db.add(Membership(org_id=org_id, user_id=user.id, role=row.role))
        row.closed_at = now
        return {"org_id": org_id, "name": org.name, "role": row.role}
