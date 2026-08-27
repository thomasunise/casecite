"""Admin user-management router.

Lets an admin list users, invite new users with an assigned role, and change
existing users' roles. Admin-only. Self-hosted: "invite" creates an active
account with a generated one-time temporary password (returned once to the
admin to hand off) since email delivery may not be configured.
"""

import asyncio
import logging
import secrets
import string
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import User as DBUser
from app.models.schemas import (
    AdminUserItem,
    AdminUserListResponse,
    InviteUserRequest,
    InviteUserResponse,
    SetUserActiveRequest,
    UpdateRolePermissionsRequest,
    UpdateUserRoleRequest,
)
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData, UserRole
from app.services.permissions import require_permission
from app.utils.ip_resolution import get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

_VALID_ROLES = {r.value for r in UserRole}


def _to_item(u: DBUser) -> AdminUserItem:
    roles = (
        u.roles
        if isinstance(u.roles, list)
        else (["attorney"] if u.roles is None else list(u.roles))
    )
    return AdminUserItem(
        id=u.id,
        email=u.email,
        name=u.name or "",
        roles=roles,
        is_active=bool(u.is_active),
        created_at=u.created_at,
        last_login=u.last_login,
    )


def _generate_temp_password() -> str:
    """Generate a random password that satisfies the standard complexity policy."""
    alphabet = string.ascii_letters + string.digits
    specials = "!@#$%^&*-_"
    core = "".join(secrets.choice(alphabet) for _ in range(14))
    # Guarantee one of each required class.
    return (
        secrets.choice(string.ascii_uppercase)
        + secrets.choice(string.ascii_lowercase)
        + secrets.choice(string.digits)
        + secrets.choice(specials)
        + core
    )


@router.get("", response_model=AdminUserListResponse)
async def list_users(
    current_user: TokenData = require_permission("admin.users"),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    """List all user accounts."""
    result = await db.execute(select(DBUser).order_by(DBUser.created_at))
    users = result.scalars().all()
    return AdminUserListResponse(users=[_to_item(u) for u in users])


@router.post("/invite", response_model=InviteUserResponse, status_code=201)
async def invite_user(
    body: InviteUserRequest,
    request: Request,
    current_user: TokenData = require_permission("admin.users"),
    db: AsyncSession = Depends(get_db),
) -> InviteUserResponse:
    """Create a user with the given role and a one-time temporary password."""
    from app.services.passwords import hash_password

    if body.role not in _VALID_ROLES:
        raise HTTPException(
            status_code=400, detail=f"Invalid role. Must be one of: {sorted(_VALID_ROLES)}"
        )

    email = body.email.lower().strip()
    existing = await db.execute(select(DBUser).where(DBUser.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    temp_password = _generate_temp_password()
    # PBKDF2 (600k iterations) is CPU-bound — run it off the event loop.
    temp_password_hash = await asyncio.to_thread(hash_password, temp_password)
    db_user = DBUser(
        id=str(uuid.uuid4()),
        email=email,
        name=body.name.strip(),
        password_hash=temp_password_hash,
        roles=[body.role],
        email_verified=True,
        is_active=True,
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    await audit_service.log_event(
        event_type=AuditEventType.USER_CREATE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="user",
        resource_id=db_user.id,
        ip_address=get_client_ip(request),
        details={"action": "invite_user", "invited_email": email, "role": body.role},
    )

    return InviteUserResponse(user=_to_item(db_user), temporary_password=temp_password)


# ── Role permissions (literal paths BEFORE the /{user_id} catch-alls) ──


async def _roles_payload() -> dict:
    """The matrix the UI renders: catalog, defaults, current, customized."""
    from app.services import permissions as perm

    matrix = await perm.get_role_permissions()
    return {
        "permissions": perm.PERMISSIONS,
        "roles": perm.ROLES,
        "defaults": {r: sorted(perm.DEFAULT_ROLE_PERMISSIONS[r]) for r in perm.ROLES},
        "assigned": {r: sorted(matrix[r]) for r in perm.ROLES},
        "customized": [r for r in perm.ROLES if matrix[r] != perm.DEFAULT_ROLE_PERMISSIONS[r]],
        "locked": {r: sorted(keys) for r, keys in perm.LOCKED.items()},
    }


@router.get("/roles")
async def get_role_permissions(
    current_user: TokenData = require_permission("admin.users"),
) -> dict:
    """Permission catalog plus each role's current and default grants."""
    return await _roles_payload()


@router.put("/roles/{role}")
async def update_role_permissions(
    role: str,
    body: UpdateRolePermissionsRequest,
    request: Request,
    current_user: TokenData = require_permission("admin.users"),
) -> dict:
    """Set one role's permission list. Locked permissions are always re-added."""
    from app.services import permissions as perm

    try:
        await perm.set_role_permissions(role, body.permissions)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await audit_service.log_event(
        event_type=AuditEventType.SETTINGS_CHANGE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="role",
        resource_id=role,
        ip_address=get_client_ip(request),
        details={
            "action": "role_permissions_set",
            "role": role,
            "permissions": sorted(body.permissions),
        },
    )
    return await _roles_payload()


@router.post("/roles/reset")
async def reset_role_permissions(
    request: Request,
    current_user: TokenData = require_permission("admin.users"),
) -> dict:
    """Drop every customization — all roles return to the shipped defaults."""
    from app.services import permissions as perm

    await perm.reset_role_permissions()

    await audit_service.log_event(
        event_type=AuditEventType.SETTINGS_CHANGE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="role",
        ip_address=get_client_ip(request),
        details={"action": "role_permissions_reset"},
    )
    return await _roles_payload()


@router.patch("/{user_id}/role", response_model=AdminUserItem)
async def update_user_role(
    user_id: str,
    body: UpdateUserRoleRequest,
    request: Request,
    current_user: TokenData = require_permission("admin.users"),
    db: AsyncSession = Depends(get_db),
) -> AdminUserItem:
    """Change a user's role. Prevents removing the last remaining admin."""
    if body.role not in _VALID_ROLES:
        raise HTTPException(
            status_code=400, detail=f"Invalid role. Must be one of: {sorted(_VALID_ROLES)}"
        )

    result = await db.execute(select(DBUser).where(DBUser.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    current_roles = target.roles if isinstance(target.roles, list) else []
    was_admin = UserRole.ADMIN.value in current_roles
    becoming_non_admin = body.role != UserRole.ADMIN.value

    # Guard against locking everyone out: don't demote the last ACTIVE admin
    # (an inactive admin can't sign in, so counting them would allow lockout).
    # JSON column membership is dialect-specific, so count in Python.
    if was_admin and becoming_non_admin and target.is_active:
        all_users = (await db.execute(select(DBUser))).scalars().all()
        active_admin_count = sum(
            1
            for u in all_users
            if u.is_active and isinstance(u.roles, list) and UserRole.ADMIN.value in u.roles
        )
        if active_admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last remaining admin.")

    target.roles = [body.role]
    await db.commit()
    await db.refresh(target)

    # Revoke the user's sessions so tokens carrying the OLD role stop working
    # immediately (roles are embedded in the access token at issue time).
    from app.middleware.security import session_manager
    from app.services.auth import auth_service

    for _session in session_manager.get_active_sessions_raw(target.id):
        auth_service.revoke_token(_session["jti"])
    session_manager.terminate_all_sessions(target.id)

    await audit_service.log_event(
        event_type=AuditEventType.USER_ROLE_CHANGE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="user",
        resource_id=target.id,
        ip_address=get_client_ip(request),
        details={"action": "update_role", "new_role": body.role},
    )

    return _to_item(target)


@router.patch("/{user_id}/active", response_model=AdminUserItem)
async def set_user_active(
    user_id: str,
    body: SetUserActiveRequest,
    request: Request,
    current_user: TokenData = require_permission("admin.users"),
    db: AsyncSession = Depends(get_db),
) -> AdminUserItem:
    """Activate or deactivate (offboard) a user account.

    A deactivated user cannot authenticate: get_current_user rejects inactive
    accounts, and their existing sessions are torn down here so access is cut
    immediately. Guards against self-lockout and disabling the last admin.
    """
    result = await db.execute(select(DBUser).where(DBUser.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not body.is_active:
        if target.id == current_user.user_id:
            raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")
        # Don't allow disabling the last remaining admin.
        target_is_admin = isinstance(target.roles, list) and UserRole.ADMIN.value in target.roles
        if target_is_admin:
            all_users = (await db.execute(select(DBUser))).scalars().all()
            active_admins = sum(
                1
                for u in all_users
                if u.is_active and isinstance(u.roles, list) and UserRole.ADMIN.value in u.roles
            )
            if active_admins <= 1:
                raise HTTPException(
                    status_code=400, detail="Cannot deactivate the last remaining admin."
                )

    target.is_active = body.is_active
    await db.commit()
    await db.refresh(target)

    # On deactivation, revoke sessions/tokens so access is cut immediately
    # rather than lingering until token expiry.
    if not body.is_active:
        from app.middleware.security import session_manager
        from app.services.auth import auth_service

        for _session in session_manager.get_active_sessions_raw(target.id):
            auth_service.revoke_token(_session["jti"])
        session_manager.terminate_all_sessions(target.id)

    await audit_service.log_event(
        event_type=AuditEventType.USER_UPDATE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="user",
        resource_id=target.id,
        ip_address=get_client_ip(request),
        details={"action": "activate" if body.is_active else "deactivate"},
    )

    return _to_item(target)


@router.get("/{user_id}/export")
async def export_user_data(
    user_id: str,
    request: Request,
    current_user: TokenData = require_permission("admin.users"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Export a user's data (profile + documents metadata + folders) as JSON.

    Supports data-portability / right-to-access requests (GDPR Art. 20 / CCPA).
    """
    from app.services.documents import document_service

    target = (await db.execute(select(DBUser).where(DBUser.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    export = {
        "profile": {
            "id": target.id,
            "email": target.email,
            "name": target.name,
            "roles": target.roles,
            "created_at": target.created_at.isoformat() if target.created_at else None,
            "last_login": target.last_login.isoformat() if target.last_login else None,
        },
        **document_service.export_user_data(user_id),
    }

    await audit_service.log_event(
        event_type=AuditEventType.DATA_EXPORT,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="user",
        resource_id=user_id,
        ip_address=get_client_ip(request),
    )
    return export


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    current_user: TokenData = require_permission("admin.users"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a user and erase their data (right-to-erasure, GDPR/CCPA).

    Purges uploaded files + vector embeddings + the encrypted key store +
    connector OAuth tokens (revoked provider-side where cheap) + per-user
    settings, then deletes the DB row (relational data cascades). Guards
    against deleting yourself or the last remaining admin.
    """
    from app.services.connectors.base import delete_user_credentials
    from app.services.documents import document_service
    from app.services.key_storage import delete_user_keys
    from app.services.user_settings import delete_user_settings

    target = (await db.execute(select(DBUser).where(DBUser.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    if target.id == current_user.user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    if target.is_active and isinstance(target.roles, list) and UserRole.ADMIN.value in target.roles:
        # Count ACTIVE admins only — an inactive admin row must not satisfy the
        # guard, or deleting the last usable admin locks the firm out. (Deleting
        # an inactive admin can't cause lockout, so the guard skips them.)
        all_users = (await db.execute(select(DBUser))).scalars().all()
        active_admin_count = sum(
            1
            for u in all_users
            if u.is_active and isinstance(u.roles, list) and UserRole.ADMIN.value in u.roles
        )
        if active_admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last remaining admin.")

    target_email = target.email

    # Revoke sessions/tokens first so access stops immediately.
    from app.middleware.security import session_manager
    from app.services.auth import auth_service

    for _session in session_manager.get_active_sessions_raw(user_id):
        auth_service.revoke_token(_session["jti"])
    session_manager.terminate_all_sessions(user_id)
    # Tombstone the user id so any still-unexpired token is rejected on every
    # worker even after the DB row (and its is_active check) is gone.
    auth_service.revoke_user(user_id)

    # Purge user-owned data outside the relational DB: documents + vectors,
    # BYOK keys, connector OAuth credential files (revoking the grant where the
    # provider offers a cheap endpoint), and the per-user settings file.
    purge_result = await document_service.purge_user_data(user_id)
    delete_user_keys(user_id)
    purge_result.update(await delete_user_credentials(user_id))
    purge_result["settings_files_deleted"] = delete_user_settings(user_id)

    # Purge user-owned rows whose tables carry user_id as a plain column with no
    # ON DELETE CASCADE to users — deleting the users row alone would orphan this
    # privileged content (chat threads, contract analyses, authority maps).
    # Children keyed by analysis_id/run_id are removed before their parent runs;
    # chat_messages cascade from chat_sessions via a real FK.
    from sqlalchemy import delete as sa_delete

    from app.models.authority_map import AuthorityMapping, AuthorityMapRun
    from app.models.chat_sessions import ChatSessionDB
    from app.models.clause_intel import (
        ClauseDeviationFinding,
        ClauseTagFinding,
        ContractAnalysisRun,
    )
    from app.models.contract_analysis import (
        ContractDeadline,
        ContractDefinedTerm,
        ContractObligation,
        ContractParty,
    )

    run_ids = (
        (
            await db.execute(
                select(ContractAnalysisRun.id).where(ContractAnalysisRun.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    if run_ids:
        for child in (
            ContractParty,
            ContractObligation,
            ContractDeadline,
            ContractDefinedTerm,
            ClauseDeviationFinding,
            ClauseTagFinding,
        ):
            await db.execute(sa_delete(child).where(child.analysis_id.in_(run_ids)))
        await db.execute(sa_delete(ContractAnalysisRun).where(ContractAnalysisRun.id.in_(run_ids)))

    am_run_ids = (
        (await db.execute(select(AuthorityMapRun.id).where(AuthorityMapRun.user_id == user_id)))
        .scalars()
        .all()
    )
    if am_run_ids:
        await db.execute(sa_delete(AuthorityMapping).where(AuthorityMapping.run_id.in_(am_run_ids)))
        await db.execute(sa_delete(AuthorityMapRun).where(AuthorityMapRun.id.in_(am_run_ids)))

    await db.execute(sa_delete(ChatSessionDB).where(ChatSessionDB.user_id == user_id))

    # Matters & memberships have no users FK (they tolerate demo/SSO accounts),
    # so purge them explicitly. Remove the user's memberships everywhere, then
    # the matters they own (which cascades those matters' remaining members).
    from app.models.matters import Matter, MatterMember

    await db.execute(sa_delete(MatterMember).where(MatterMember.user_id == user_id))
    await db.execute(sa_delete(Matter).where(Matter.owner_id == user_id))

    # Delete the DB row; ON DELETE CASCADE removes FK-linked relational rows.
    await db.delete(target)
    await db.commit()

    await audit_service.log_event(
        event_type=AuditEventType.USER_DELETE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="user",
        resource_id=user_id,
        ip_address=get_client_ip(request),
        details={"deleted_email": target_email, **purge_result},
    )
    await audit_service.log_event(
        event_type=AuditEventType.DATA_DELETION,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="user",
        resource_id=user_id,
        ip_address=get_client_ip(request),
        details=purge_result,
    )
    return {"status": "deleted", "user_id": user_id, **purge_result}
