"""Matter (collaboration / sharing) endpoints.

Lets a user create matters, see the matters they belong to, and — as the matter
owner — invite or remove colleagues by email. Membership is what grants access
to a matter's documents, chats, and analyses (see app/services/matters.py).

Thin HTTP layer: all membership logic lives in the service. Literal routes are
defined before the parameterized /{matter_id} catch-alls.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.auth import User as DBUser
from app.models.matters import Matter
from app.models.schemas import (
    AddMatterMemberRequest,
    CreateMatterRequest,
    MatterDetailResponse,
    MatterListResponse,
    MatterMemberResponse,
    MatterResponse,
)
from app.services import matters as matters_service
from app.services.auth import TokenData, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/matters", tags=["matters"])


async def _to_response(db: AsyncSession, matter: Matter, caller_id: str) -> MatterResponse:
    role = "owner" if matter.owner_id == caller_id else "member"
    return MatterResponse(
        id=matter.id,
        name=matter.name,
        client_name=matter.client_name,
        is_personal=matter.is_personal,
        owner_id=matter.owner_id,
        role=role,
        member_count=await matters_service.member_count(db, matter.id),
        created_at=matter.created_at,
    )


async def _members_with_identity(db: AsyncSession, matter_id: str) -> list[MatterMemberResponse]:
    members = await matters_service.list_members(db, matter_id)
    user_ids = [m.user_id for m in members]
    identities: dict[str, DBUser] = {}
    if user_ids:
        rows = (await db.execute(select(DBUser).where(DBUser.id.in_(user_ids)))).scalars().all()
        identities = {u.id: u for u in rows}
    out = []
    for m in members:
        u = identities.get(m.user_id)
        out.append(
            MatterMemberResponse(
                user_id=m.user_id,
                email=u.email if u else None,
                name=u.name if u else None,
                role=m.role,
            )
        )
    return out


async def _require_owned_matter(db: AsyncSession, matter_id: str, caller_id: str) -> Matter:
    """Return the matter only if the caller is its owner; else 404 (no existence leak)."""
    matter = await matters_service.get_matter(db, matter_id)
    if matter is None or matter.owner_id != caller_id:
        raise HTTPException(status_code=404, detail="Matter not found")
    return matter


@router.get("", response_model=MatterListResponse)
async def list_matters(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatterListResponse:
    """List the matters the caller belongs to (personal first, then newest)."""
    matters = await matters_service.list_matters_for_user(db, current_user.user_id)
    await db.commit()  # list_matters_for_user may have created the personal matter
    return MatterListResponse(
        matters=[await _to_response(db, m, current_user.user_id) for m in matters]
    )


@router.post("", response_model=MatterResponse, status_code=201)
async def create_matter(
    body: CreateMatterRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatterResponse:
    """Create a shared matter owned by the caller."""
    matter = await matters_service.create_matter(
        db, owner_id=current_user.user_id, name=body.name, client_name=body.client_name
    )
    await db.commit()
    return await _to_response(db, matter, current_user.user_id)


@router.get("/{matter_id}", response_model=MatterDetailResponse)
async def get_matter(
    matter_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatterDetailResponse:
    """A matter with its members. Only accessible to members (else 404)."""
    if not await matters_service.is_member(db, matter_id, current_user.user_id):
        raise HTTPException(status_code=404, detail="Matter not found")
    matter = await matters_service.get_matter(db, matter_id)
    base = await _to_response(db, matter, current_user.user_id)
    return MatterDetailResponse(
        **base.model_dump(),
        members=await _members_with_identity(db, matter_id),
    )


@router.post("/{matter_id}/members", response_model=MatterDetailResponse)
async def add_matter_member(
    matter_id: str,
    body: AddMatterMemberRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatterDetailResponse:
    """Invite a colleague (by email) to a matter. Owner only."""
    matter = await _require_owned_matter(db, matter_id, current_user.user_id)
    if matter.is_personal:
        raise HTTPException(status_code=400, detail="A personal matter cannot be shared.")

    email = body.email.lower().strip()
    invitee = (await db.execute(select(DBUser).where(DBUser.email == email))).scalar_one_or_none()
    if invitee is None:
        raise HTTPException(status_code=404, detail="No user with that email address.")

    try:
        await matters_service.add_member(db, matter_id, invitee.id, added_by=current_user.user_id)
    except matters_service.MatterAccessError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()

    base = await _to_response(db, matter, current_user.user_id)
    return MatterDetailResponse(
        **base.model_dump(),
        members=await _members_with_identity(db, matter_id),
    )


@router.delete("/{matter_id}/members/{user_id}", response_model=MatterDetailResponse)
async def remove_matter_member(
    matter_id: str,
    user_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatterDetailResponse:
    """Remove a member from a matter. Owner only; the owner cannot be removed."""
    matter = await _require_owned_matter(db, matter_id, current_user.user_id)
    try:
        removed = await matters_service.remove_member(db, matter_id, user_id)
    except matters_service.MatterAccessError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not removed:
        raise HTTPException(status_code=404, detail="That user is not a member of this matter.")
    await db.commit()

    base = await _to_response(db, matter, current_user.user_id)
    return MatterDetailResponse(
        **base.model_dump(),
        members=await _members_with_identity(db, matter_id),
    )


@router.delete("/{matter_id}")
async def delete_matter(
    matter_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a matter and its memberships. Owner only; personal matters can't be deleted.

    Content filed under the matter (documents, chats, analyses) is NOT deleted;
    it reverts to owner-only visibility as its matter no longer exists.
    """
    matter = await _require_owned_matter(db, matter_id, current_user.user_id)
    if matter.is_personal:
        raise HTTPException(status_code=400, detail="A personal matter cannot be deleted.")
    await db.delete(matter)  # memberships cascade via MatterMember.matter_id FK
    await db.commit()
    return {"status": "deleted", "id": matter_id}
