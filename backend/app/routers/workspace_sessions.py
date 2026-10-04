"""Universal History — restorable workspace-session snapshots.

Every surface (contracts incl. the drafting workspace, each legal tool's
search + result-chat, judge intel, case pages) saves its working state here as
a JSON snapshot; the History panel lists them and the client rehydrates the
exact session on click. Snapshots are per-user and capped in size.
"""

import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.schemas import WorkspaceSessionCreate, WorkspaceSessionUpdate
from app.models.tracking import WorkspaceSessionDB
from app.routers._matter_deps import accessible_matter_ids
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData, get_current_user
from app.utils.ip_resolution import get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspace-sessions", tags=["workspace-sessions"])

# Snapshots carry conversations, tool results, and draft texts — generous but
# bounded, so one runaway session can't bloat the database.
MAX_PAYLOAD_BYTES = 2_000_000


def _check_payload(payload: dict) -> None:
    size = len(json.dumps(payload, default=str))
    if size > MAX_PAYLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Session snapshot too large to save.",
        )


def _to_summary(row: WorkspaceSessionDB) -> dict:
    return {
        "id": row.id,
        "surface": row.surface,
        "title": row.title,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def _get_own(
    db: AsyncSession,
    session_id: str,
    user_id: str,
    accessible_matter_ids: set[str] | None = None,
) -> WorkspaceSessionDB:
    scope = WorkspaceSessionDB.user_id == user_id
    if accessible_matter_ids:
        scope = or_(scope, WorkspaceSessionDB.matter_id.in_(list(accessible_matter_ids)))
    row = (
        await db.execute(
            select(WorkspaceSessionDB).where(WorkspaceSessionDB.id == session_id, scope)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return row


@router.get("")
async def list_sessions(
    limit: int = Query(100, ge=1, le=200),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    accessible_matters: set[str] = Depends(accessible_matter_ids),
) -> dict:
    """List the caller's workspace sessions (own + shared matters), newest first."""
    scope = WorkspaceSessionDB.user_id == current_user.user_id
    if accessible_matters:
        scope = or_(scope, WorkspaceSessionDB.matter_id.in_(list(accessible_matters)))
    rows = (
        (
            await db.execute(
                select(WorkspaceSessionDB)
                .where(scope)
                .order_by(WorkspaceSessionDB.updated_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {"sessions": [_to_summary(r) for r in rows]}


@router.post("", status_code=201)
async def create_session(
    body: WorkspaceSessionCreate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new workspace-session snapshot."""
    _check_payload(body.payload)
    row = WorkspaceSessionDB(
        id=str(uuid.uuid4()),
        user_id=current_user.user_id,
        surface=body.surface,
        title=body.title,
        payload=body.payload,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_summary(row)


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    accessible_matters: set[str] = Depends(accessible_matter_ids),
) -> dict:
    """One session with its full payload, for rehydration (own or shared matter)."""
    row = await _get_own(
        db, session_id, current_user.user_id, accessible_matter_ids=accessible_matters
    )
    await audit_service.log_event(
        event_type=AuditEventType.DATA_ACCESS,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="workspace_session",
        resource_id=session_id,
        ip_address=get_client_ip(request),
        details={"surface": row.surface},
    )
    return {**_to_summary(row), "payload": row.payload or {}}


@router.put("/{session_id}")
async def update_session(
    session_id: str,
    body: WorkspaceSessionUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update a session's title and/or payload (the autosave upsert path)."""
    row = await _get_own(db, session_id, current_user.user_id)
    if body.payload is not None:
        _check_payload(body.payload)
        row.payload = body.payload
    if body.title is not None:
        row.title = body.title
    row.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(row)
    return _to_summary(row)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete one of the user's sessions."""
    row = await _get_own(db, session_id, current_user.user_id)
    surface = row.surface
    await db.delete(row)
    await db.commit()
    await audit_service.log_event(
        event_type=AuditEventType.DATA_DELETION,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="workspace_session",
        resource_id=session_id,
        ip_address=get_client_ip(request),
        details={"surface": surface},
    )
    return {"status": "deleted", "id": session_id}
