"""Account-owned projects."""

from datetime import UTC

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from . import platform_runtime as store
from .identity import NamedResource, require_user
from .platform_db import (
    Project, bind_owner, bind_project, personal_namespace_id,
    personal_projects_enabled, platform_session, utc_now,
)
from .scan_contracts import Identifier
from .scan_events import MESSAGES

router = APIRouter(prefix="/api/platform", tags=["Personal projects"])


def personal_user(request):
    if not personal_projects_enabled():
        raise HTTPException(404, "المسار غير متاح.")
    return require_user(request)


def project_view(project):
    created = project.created_at
    updated = project.updated_at or created
    return {
        "id": project.id, "name": project.name, "role": "owner",
        "created_at": (created if created.tzinfo else created.replace(tzinfo=UTC)).astimezone(UTC),
        "updated_at": (updated if updated.tzinfo else updated.replace(tzinfo=UTC)).astimezone(UTC),
    }


def list_owned(user_id, archived=False):
    """Active projects by name, or the account's deleted projects, newest deletion first."""
    with platform_session() as db:
        bind_owner(db, user_id)
        if archived:
            query = select(Project).where(Project.owner_user_id == user_id, Project.deleted_at.is_not(None)
                                          ).order_by(Project.deleted_at.desc(), Project.id)
        else:
            query = select(Project).where(Project.owner_user_id == user_id, Project.deleted_at.is_(None)
                                          ).order_by(Project.name, Project.id)
        return {"projects": [project_view(project) | ({"deleted_at": _utc(project.deleted_at)} if archived else {})
                             for project in db.scalars(query)]}


def _utc(value):
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)


def owned(db, project_id, user_id, *, lock=False):
    bind_owner(db, user_id)
    query = select(Project).where(
        Project.id == project_id, Project.owner_user_id == user_id, Project.deleted_at.is_(None),
    )
    project = db.scalar(query.with_for_update() if lock else query)
    if not project:
        raise HTTPException(404, "المشروع غير متاح.")
    return project


@router.post("/projects", status_code=201)
def create_project(body: NamedResource, request: Request):
    user = personal_user(request)
    with platform_session() as db:
        bind_owner(db, user.id)
        # Serialize first-project creation for this account. Existing composite FKs
        # still use the internal organization ID until the legacy schema is retired.
        namespace = personal_namespace_id(db, user.id, create=True)
        if not namespace:
            raise HTTPException(401, "الحساب غير متاح.")
        project = Project(name=body.name, org_id=namespace, owner_user_id=user.id)
        db.add(project)
        db.flush()
        return project_view(project)


@router.get("/projects/{project_id}")
def project_detail(project_id: Identifier, request: Request):
    user = personal_user(request)
    with platform_session() as db:
        return project_view(owned(db, project_id, user.id))


@router.patch("/projects/{project_id}")
def rename_project(project_id: Identifier, body: NamedResource, request: Request):
    user = personal_user(request)
    with platform_session() as db:
        project = owned(db, project_id, user.id, lock=True)
        project.name = body.name
        project.updated_at = utc_now()
        return project_view(project)


@router.delete("/projects/{project_id}", status_code=204)
def archive_project(project_id: Identifier, request: Request):
    user = personal_user(request)
    with platform_session() as db:
        project = owned(db, project_id, user.id, lock=True)
        bind_project(db, project.org_id, project.id, owner_user_id=user.id)
        pending = db.execute(select(store.scans).where(
            store.scope(store.scans, project.org_id, project.id),
            store.scans.c.state.in_(("queued", "running")),
        ).order_by(store.scans.c.id).with_for_update()).mappings().all()
        for scan in pending:
            store.close_scan(db, scan, "cancelled", MESSAGES["scan.cancelled_project_deleted"])
        project.deleted_at = project.updated_at = utc_now()


@router.post("/projects/{project_id}/restore")
def restore_project(project_id: Identifier, request: Request):
    """Bring a deleted project back. Scans cancelled by the deletion stay cancelled."""
    user = personal_user(request)
    with platform_session() as db:
        bind_owner(db, user.id)
        project = db.scalar(select(Project).where(
            Project.id == project_id, Project.owner_user_id == user.id, Project.deleted_at.is_not(None),
        ).with_for_update())
        if not project:
            raise HTTPException(404, "المشروع غير متاح.")
        project.deleted_at = None
        project.updated_at = utc_now()
        return project_view(project)
