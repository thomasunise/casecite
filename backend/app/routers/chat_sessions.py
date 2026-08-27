"""Persistent chat session endpoints.

Thin HTTP layer over app.services.chat_sessions — all business logic and
tenant isolation live in the service. Literal routes are defined before the
parameterized /{session_id} catch-alls.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.schemas import (
    ChatSessionDetail,
    ChatSessionListResponse,
    ChatSessionSummary,
    CreateChatSessionRequest,
)
from app.routers._matter_deps import accessible_matter_ids
from app.services import chat_sessions as chat_session_service
from app.services import matters as matters_service
from app.services.auth import TokenData
from app.services.permissions import require_permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat/sessions", tags=["chat-sessions"])


@router.get("", response_model=ChatSessionListResponse)
async def list_chat_sessions(
    limit: int = Query(50, ge=1, le=200),
    current_user: TokenData = require_permission("chat.use"),
    accessible_matters: set[str] = Depends(accessible_matter_ids),
) -> ChatSessionListResponse:
    """List the caller's chat sessions (own + shared matters), newest first."""
    sessions = await chat_session_service.list_sessions(
        current_user.user_id, limit=limit, accessible_matter_ids=accessible_matters
    )
    return {"sessions": sessions}


@router.post("", response_model=ChatSessionSummary)
async def create_chat_session(
    request: CreateChatSessionRequest,
    current_user: TokenData = require_permission("chat.use"),
    db: AsyncSession = Depends(get_db),
) -> ChatSessionSummary:
    """Create a new (empty) chat session, optionally filed under a shared matter."""
    if request.matter_id and not await matters_service.is_member(
        db, request.matter_id, current_user.user_id
    ):
        raise HTTPException(status_code=403, detail="You are not a member of the specified matter.")
    return await chat_session_service.create_session(
        current_user.user_id, request.title, matter_id=request.matter_id
    )


@router.get("/{session_id}", response_model=ChatSessionDetail)
async def get_chat_session(
    session_id: str,
    current_user: TokenData = require_permission("chat.use"),
    accessible_matters: set[str] = Depends(accessible_matter_ids),
) -> ChatSessionDetail:
    """Return the full conversation thread for a session the caller may access."""
    session = await chat_session_service.get_session_with_messages(
        session_id, current_user.user_id, accessible_matter_ids=accessible_matters
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@router.delete("/{session_id}")
async def delete_chat_session(
    session_id: str,
    current_user: TokenData = require_permission("chat.use"),
    accessible_matters: set[str] = Depends(accessible_matter_ids),
) -> dict:
    """Delete a session (own or shared via a matter) and all its messages."""
    deleted = await chat_session_service.delete_session(
        session_id, current_user.user_id, accessible_matter_ids=accessible_matters
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"status": "deleted", "id": session_id}
