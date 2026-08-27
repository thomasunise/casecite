"""
TOTP MFA router.

Enrollment/management (setup, enable, disable, status) require an authenticated
session. The second login step (verify) is public: it takes the short-lived MFA
challenge issued by /auth/login plus a TOTP or recovery code, and returns full
tokens. See app.services.mfa.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.security import account_lockout, session_manager
from app.models.db_models import User as DBUser
from app.models.responses.auth import LoginResponse, UserInfo
from app.models.schemas import (
    MfaDisableRequest,
    MfaEnableRequest,
    MfaEnableResponse,
    MfaSetupResponse,
    MfaStatusResponse,
    MfaVerifyRequest,
)
from app.services import mfa as mfa_service
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData, User, UserRole, auth_service, get_current_user
from app.utils.ip_resolution import get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/mfa", tags=["mfa"])


async def _load_user(db: AsyncSession, user_id: str) -> DBUser:
    result = await db.execute(select(DBUser).where(DBUser.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/status", response_model=MfaStatusResponse)
async def mfa_status(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MfaStatusResponse:
    """Whether MFA is currently enabled for the signed-in user."""
    user = await _load_user(db, current_user.user_id)
    return MfaStatusResponse(
        enabled=bool(getattr(user, "mfa_enabled", False)),
        recovery_codes_remaining=len(user.mfa_recovery_codes or []),
    )


@router.post("/setup", response_model=MfaSetupResponse)
async def mfa_setup(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MfaSetupResponse:
    """Begin enrollment: generate a secret (stored encrypted, not yet enabled)."""
    user = await _load_user(db, current_user.user_id)
    if user.mfa_enabled:
        # Never let a session-only attacker reset/disable an active second factor.
        # Re-enrollment requires disabling first, which demands a valid code.
        raise HTTPException(
            status_code=409,
            detail="MFA is already enabled. Disable it (requires a valid code) before re-enrolling.",
        )
    secret = mfa_service.generate_secret()
    user.mfa_secret = mfa_service.encrypt_secret(secret)
    # Not enabled until the user proves possession via /enable.
    user.mfa_enabled = False
    await db.commit()
    return MfaSetupResponse(
        secret=secret,
        provisioning_uri=mfa_service.provisioning_uri(secret, user.email),
    )


@router.post("/enable", response_model=MfaEnableResponse)
async def mfa_enable(
    body: MfaEnableRequest,
    request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MfaEnableResponse:
    """Confirm enrollment with a code, enable MFA, and return recovery codes once."""
    user = await _load_user(db, current_user.user_id)
    if not user.mfa_secret:
        raise HTTPException(status_code=400, detail="Start MFA setup first.")

    secret = mfa_service.decrypt_secret(user.mfa_secret)
    if not mfa_service.verify_totp(secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid code. Try again.")

    plaintext_codes, hashed_codes = mfa_service.generate_recovery_codes()
    user.mfa_enabled = True
    user.mfa_recovery_codes = hashed_codes
    await db.commit()

    await audit_service.log_event(
        event_type=AuditEventType.MFA_ENABLED,
        user_id=user.id,
        user_email=user.email,
        ip_address=get_client_ip(request),
    )
    return MfaEnableResponse(recovery_codes=plaintext_codes)


@router.post("/disable")
async def mfa_disable(
    body: MfaDisableRequest,
    request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Disable MFA after proving a current TOTP or recovery code."""
    user = await _load_user(db, current_user.user_id)
    if not user.mfa_enabled or not user.mfa_secret:
        return {"status": "mfa_not_enabled"}

    secret = mfa_service.decrypt_secret(user.mfa_secret)
    ok = mfa_service.verify_totp(secret, body.code)
    if not ok:
        consumed, _remaining = mfa_service.consume_recovery_code(
            body.code, user.mfa_recovery_codes or []
        )
        ok = consumed
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid code.")

    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_recovery_codes = None
    await db.commit()

    await audit_service.log_event(
        event_type=AuditEventType.MFA_DISABLED,
        user_id=user.id,
        user_email=user.email,
        ip_address=get_client_ip(request),
    )
    return {"status": "mfa_disabled"}


@router.post("/recovery-codes", response_model=MfaEnableResponse)
async def mfa_regenerate_recovery_codes(
    body: MfaEnableRequest,
    request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MfaEnableResponse:
    """Regenerate recovery codes after proving a current TOTP code.

    TOTP only — a stolen recovery code must not be able to mint a fresh set.
    All previous codes are invalidated.
    """
    user = await _load_user(db, current_user.user_id)
    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA is not enabled.")

    secret = mfa_service.decrypt_secret(user.mfa_secret)
    if not mfa_service.verify_totp(secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid code.")

    plaintext_codes, hashed_codes = mfa_service.generate_recovery_codes()
    user.mfa_recovery_codes = hashed_codes
    await db.commit()

    await audit_service.log_event(
        event_type=AuditEventType.MFA_ENABLED,
        user_id=user.id,
        user_email=user.email,
        details={"action": "recovery_codes_regenerated"},
        ip_address=get_client_ip(request),
    )
    return MfaEnableResponse(recovery_codes=plaintext_codes)


@router.post("/verify", response_model=LoginResponse)
async def mfa_verify(
    body: MfaVerifyRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Second login step: exchange the MFA challenge + code for tokens."""
    from app.routers.auth import _set_auth_cookies

    user_id = mfa_service.verify_challenge_token(body.mfa_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="MFA session expired. Please sign in again.")

    user_row = await _load_user(db, user_id)
    if not user_row.is_active or not user_row.mfa_enabled or not user_row.mfa_secret:
        raise HTTPException(status_code=401, detail="MFA is not active for this account.")

    # Per-account brute-force brake: failed second-factor attempts count toward
    # the same lockout as failed passwords, so a stolen password can't be paired
    # with distributed TOTP guessing across many IPs.
    if account_lockout.is_account_locked(user_row.email):
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Try again later.",
        )

    secret = mfa_service.decrypt_secret(user_row.mfa_secret)
    used_recovery = False
    if not mfa_service.verify_totp(secret, body.code):
        consumed, remaining = mfa_service.consume_recovery_code(
            body.code, user_row.mfa_recovery_codes or []
        )
        if not consumed:
            account_lockout.record_login_failure(user_row.email)
            await audit_service.log_event(
                event_type=AuditEventType.LOGIN_FAILURE,
                user_id=user_row.id,
                user_email=user_row.email,
                details={"method": "mfa", "reason": "invalid_code"},
                ip_address=get_client_ip(request),
                success=False,
            )
            raise HTTPException(status_code=401, detail="Invalid code.")
        user_row.mfa_recovery_codes = remaining
        used_recovery = True
        await db.commit()

    # Spend the challenge now that the second factor is proven — a completed
    # challenge must not be replayable to mint a second set of tokens.
    if not mfa_service.consume_challenge_token(body.mfa_token):
        raise HTTPException(status_code=401, detail="MFA session expired. Please sign in again.")

    user = User(
        id=user_row.id,
        email=user_row.email,
        name=user_row.name or "",
        roles=[UserRole(r) for r in (user_row.roles or ["attorney"])],
        last_login=datetime.now(UTC),
    )
    access_token = auth_service.create_access_token(user)
    refresh_token = auth_service.create_refresh_token(user)
    token_data = auth_service.verify_token(access_token)
    session_manager.create_session(
        user_id=user.id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        jti=token_data.jti,
    )
    account_lockout.clear_account_lockout(user.email)

    await audit_service.log_event(
        event_type=AuditEventType.LOGIN_SUCCESS,
        user_id=user.id,
        user_email=user.email,
        details={"method": "mfa", "recovery_code": used_recovery},
        ip_address=get_client_ip(request),
    )

    _set_auth_cookies(request, response, access_token, refresh_token)
    return LoginResponse(
        access_token=access_token,
        expires_in=int(auth_service.access_token_expire.total_seconds()),
        user=UserInfo(
            id=user.id,
            email=user.email,
            name=user.name,
            roles=[r.value for r in user.roles],
        ),
    )
