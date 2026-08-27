"""Shared FastAPI dependency for matter-scoped access.

Resolves the set of matters the caller may access (their personal matter plus
any shared matters they belong to). Injected into resource reads so a member
sees content shared with them via a matter. Depends only on authentication —
each endpoint's own require_permission still gates the action.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import matters as matters_service
from app.services.auth import get_current_user


async def accessible_matter_ids(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> set[str]:
    return set(await matters_service.get_member_matter_ids(db, current_user.user_id))
