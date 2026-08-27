"""
Authentication Router

Provides:
- Email/password login, registration, and MFA challenge flow
- Azure AD SSO login (backend exchange)
- Token refresh, logout with session termination, session management
- Password change and reset
"""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from jwt.exceptions import PyJWTError as JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.csrf import request_is_https
from app.middleware.security import account_lockout, session_manager
from app.models.db_models import User as DBUser
from app.models.responses.auth import (
    AzureConfigResponse,
    CurrentUserResponse,
    LoginResponse,
    ResetTokenValidationResponse,
    SessionsResponse,
    TokenRefreshResponse,
)
from app.models.responses.common import MessageResponse, StatusResponse
from app.models.schemas import (
    AzureLoginRequest,
    ChangePasswordRequest,
    DemoLoginRequest,
    EmailLoginRequest,
    ForgotPasswordRequest,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyResetTokenRequest,
)
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData, User, UserRole, auth_service, get_current_user
from app.utils.ip_resolution import get_client_ip

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = logging.getLogger(__name__)

# Hardcoded account for the dev-only login (POST /auth/demo/login, DEBUG=true only).
DEV_ACCOUNT_EMAIL = "dev@localhost"

# Fixed hash used to equalize login timing when the email is unknown, so an
# attacker can't distinguish "no such user" from "wrong password" by response
# time. Computed once, lazily, to avoid paying the PBKDF2 cost at import.
_DUMMY_PASSWORD_HASH: str | None = None


def _dummy_password_hash() -> str:
    global _DUMMY_PASSWORD_HASH
    if _DUMMY_PASSWORD_HASH is None:
        from app.services.passwords import hash_password

        _DUMMY_PASSWORD_HASH = hash_password("timing-attack-equalizer-not-a-real-secret")
    return _DUMMY_PASSWORD_HASH


def _set_auth_cookies(
    request: Request, response: Response, access_token: str, refresh_token: str
) -> None:
    """Set httpOnly secure cookies for access and refresh tokens."""
    secure = request_is_https(request)  # Secure only when served over HTTPS
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=3600,
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=604800,  # 7 days
        # Scoped to the auth router (not just /refresh) so /auth/logout also
        # receives it and can revoke the refresh token server-side.
        path="/api/v1/auth",
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear httpOnly auth cookies on logout."""
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    # Also clear the pre-broadening path so sessions issued before the path
    # change don't keep a stale (already-revoked) cookie around.
    response.delete_cookie("refresh_token", path="/api/v1/auth/refresh")


@router.post("/demo/login", response_model=LoginResponse)
async def dev_login(request: Request, response: Response, body: DemoLoginRequest) -> LoginResponse:
    """
    DEV LOGIN (DEBUG=true only).

    Signs in a hardcoded local-development account (DEV_ACCOUNT_EMAIL /
    password "demo") without touching the users table. Refuses (403) unless
    DEBUG=true, so it can never be a bypass on a production instance.
    """
    from app.config import settings as app_settings

    if not app_settings.debug:
        await audit_service.log_event(
            event_type=AuditEventType.LOGIN_FAILURE,
            user_email=body.email,
            details={"method": "dev", "reason": "dev_login_disabled"},
            ip_address=get_client_ip(request),
            success=False,
        )
        raise HTTPException(status_code=403, detail="Dev login is disabled")

    import logging as _logging

    _logging.getLogger(__name__).warning(
        "DEV LOGIN (DEBUG=true only) used from IP %s", get_client_ip(request)
    )

    # Hardcoded local-development account — only reachable when DEBUG=true
    DEV_ACCOUNTS = {
        DEV_ACCOUNT_EMAIL: {
            "password": "demo",  # nosec B105 - Intentional dev-only credential
            "id": "dev-user-1",
            "name": "Dev User",
            "roles": [UserRole.VIEWER],
        },
    }

    account = DEV_ACCOUNTS.get(body.email)
    if not account or body.password != account["password"]:
        await audit_service.log_event(
            event_type=AuditEventType.LOGIN_FAILURE,
            user_email=body.email,
            details={"method": "dev", "reason": "invalid_dev_credentials"},
            ip_address=get_client_ip(request),
            success=False,
        )
        raise HTTPException(status_code=401, detail="Invalid dev credentials")

    user = User(
        id=account["id"],
        email=body.email,
        name=account["name"],
        roles=account["roles"],
        last_login=datetime.now(UTC),
    )

    access_token = auth_service.create_access_token(user)
    refresh_token = auth_service.create_refresh_token(user)

    # Create session
    token_data = auth_service.verify_token(access_token)
    session_manager.create_session(
        user_id=user.id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        jti=token_data.jti,
    )

    await audit_service.log_event(
        event_type=AuditEventType.LOGIN_SUCCESS,
        user_id=user.id,
        user_email=user.email,
        details={"method": "demo"},
        ip_address=get_client_ip(request),
    )

    _set_auth_cookies(request, response, access_token, refresh_token)

    from app.models.responses.auth import UserInfo

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


@router.post("/register", response_model=LoginResponse, status_code=201)
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Self-hosted account registration.

    Creates a user with the default 'attorney' role and issues login tokens
    immediately. There is no email verification gate, no trial period, no
    fingerprinting — operators of self-hosted installs control access via
    network policy or by disabling registration entirely.
    """
    import secrets
    import uuid

    from app.config import settings
    from app.services.password_policy import validate_password
    from app.services.passwords import hash_password

    email = body.email.lower().strip()

    existing = await db.execute(select(DBUser).where(DBUser.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    pw_errors = validate_password(body.password)
    if pw_errors:
        raise HTTPException(status_code=400, detail="; ".join(pw_errors))

    # The very first account on a fresh install becomes the admin so there is
    # always someone who can manage users and instance settings.
    from sqlalchemy import func

    user_count = (await db.execute(select(func.count()).select_from(DBUser))).scalar_one()

    if user_count == 0:
        # Bootstrapping the first (admin) account. If the operator configured a
        # bootstrap token, require it so an attacker who reaches a fresh instance
        # first cannot seize the admin slot.
        if settings.registration_bootstrap_token:
            provided = (body.bootstrap_token or "").strip()
            if not secrets.compare_digest(provided, settings.registration_bootstrap_token):
                await audit_service.log_event(
                    event_type=AuditEventType.SECURITY_ALERT,
                    user_email=email,
                    details={"reason": "invalid_bootstrap_token"},
                    ip_address=get_client_ip(request),
                )
                raise HTTPException(status_code=403, detail="A valid bootstrap token is required.")
    else:
        # Subsequent registrations are only allowed when registration is
        # explicitly enabled (or in local development). This prevents anyone
        # reachable on the network from self-provisioning a full-access account.
        if not (settings.allow_registration or settings.debug):
            raise HTTPException(
                status_code=403,
                detail="Self-service registration is disabled. Ask an administrator for an invite.",
            )

    initial_roles = ["admin"] if user_count == 0 else ["attorney"]

    # PBKDF2 (600k iterations) is CPU-bound — run it off the event loop.
    password_hash = await asyncio.to_thread(hash_password, body.password)

    db_user = DBUser(
        id=str(uuid.uuid4()),
        email=email,
        name=body.name.strip(),
        password_hash=password_hash,
        roles=initial_roles,
        company=(body.company or "").strip() or None,
        email_verified=True,
        is_active=True,
        # Naive UTC to match the TIMESTAMP WITHOUT TIME ZONE column (asyncpg rejects
        # tz-aware values into naive columns; SQLite tolerated it, Postgres does not).
        password_changed_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    user = User(
        id=db_user.id,
        email=db_user.email,
        name=db_user.name or "",
        roles=[UserRole(r) for r in initial_roles],
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

    await audit_service.log_event(
        event_type=AuditEventType.USER_CREATE,
        user_id=user.id,
        user_email=user.email,
        details={"method": "self_hosted_register"},
        ip_address=get_client_ip(request),
    )

    _set_auth_cookies(request, response, access_token, refresh_token)

    from app.models.responses.auth import UserInfo

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


@router.post("/login", response_model=LoginResponse)
async def email_login(
    request: Request,
    response: Response,
    body: EmailLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """
    Login with email and password.
    For users who signed up via the trial signup flow.
    """
    import logging

    from app.services.passwords import verify_password

    logger = logging.getLogger(__name__)

    # Check account-level lockout before attempting authentication
    if account_lockout.is_account_locked(body.email):
        await audit_service.log_event(
            event_type=AuditEventType.ACCESS_DENIED,
            user_email=body.email,
            details={"method": "email", "reason": "account_locked"},
            ip_address=get_client_ip(request),
            success=False,
        )
        raise HTTPException(
            status_code=429,
            detail="Account temporarily locked due to too many failed attempts. Try again in 15 minutes.",
        )

    try:
        result = await db.execute(select(DBUser).where(DBUser.email == body.email.lower().strip()))
        db_user = result.scalar_one_or_none()

        if not db_user or not db_user.password_hash:
            # Burn the same PBKDF2 work as the valid-user path so response time
            # doesn't reveal whether the account exists (user enumeration).
            dummy_hash = await asyncio.to_thread(_dummy_password_hash)
            await asyncio.to_thread(verify_password, body.password, dummy_hash)
            account_lockout.record_login_failure(body.email)
            await audit_service.log_event(
                event_type=AuditEventType.LOGIN_FAILURE,
                user_email=body.email,
                details={"method": "email", "reason": "user_not_found"},
                ip_address=get_client_ip(request),
                success=False,
            )
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not await asyncio.to_thread(verify_password, body.password, db_user.password_hash):
            account_lockout.record_login_failure(body.email)
            await audit_service.log_event(
                event_type=AuditEventType.LOGIN_FAILURE,
                user_email=body.email,
                details={"method": "email", "reason": "invalid_password"},
                ip_address=get_client_ip(request),
                success=False,
            )
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not db_user.is_active:
            raise HTTPException(status_code=403, detail="Account is disabled")

        # If MFA is enabled, the password is only the first factor. Return a
        # short-lived challenge instead of tokens; /auth/mfa/verify completes it.
        if getattr(db_user, "mfa_enabled", False):
            from app.services import mfa as mfa_service

            account_lockout.clear_account_lockout(body.email)  # password was correct
            challenge = mfa_service.create_challenge_token(db_user.id)
            await audit_service.log_event(
                event_type=AuditEventType.MFA_CHALLENGE,
                user_id=db_user.id,
                user_email=db_user.email,
                ip_address=get_client_ip(request),
            )
            return JSONResponse(
                status_code=200,
                content={"mfa_required": True, "mfa_token": challenge},
            )

        # Issue tokens directly
        roles = [UserRole(r) for r in (db_user.roles or ["attorney"])]
        user = User(
            id=db_user.id,
            email=db_user.email,
            name=db_user.name or "",
            roles=roles,
            last_login=datetime.now(UTC),
        )

        access_token = auth_service.create_access_token(user)
        refresh_token = auth_service.create_refresh_token(user)

        # Create session (matching what login_with_azure does)
        token_data = auth_service.verify_token(access_token)
        session_manager.create_session(
            user_id=user.id,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
            jti=token_data.jti,
        )

        # Clear account lockout on successful login
        account_lockout.clear_account_lockout(body.email)

        await audit_service.log_event(
            event_type=AuditEventType.LOGIN_SUCCESS,
            user_id=user.id,
            user_email=user.email,
            details={"method": "email"},
            ip_address=get_client_ip(request),
        )

        # Set httpOnly cookies (refresh token only in cookie, not body)
        _set_auth_cookies(request, response, access_token, refresh_token)

        from app.models.responses.auth import UserInfo

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
    except HTTPException:
        raise
    except (ValueError, KeyError, OSError, RuntimeError) as e:
        logger.debug(f"Login error details: {e}", exc_info=True)
        logger.error("Login failed for user")
        raise HTTPException(status_code=500, detail="Login failed. Please try again.")


@router.post("/azure/login", response_model=LoginResponse)
async def login_with_azure(
    request: Request,
    response: Response,
    body: AzureLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """
    Login using Azure AD token.

    The frontend should:
    1. Redirect user to Azure AD login
    2. Receive Azure token after successful auth
    3. Send that token here to get our JWT tokens

    Azure AD only proves WHO the caller is. WHAT they may do comes from the
    local account row: tokens are minted from ``users.roles`` (so an admin's
    demotion or promotion applies on the next login, exactly as for password
    accounts), and a first-time SSO user is provisioned with
    ``AZURE_SSO_DEFAULT_ROLE`` (default ``viewer``) — or refused when
    ``AZURE_SSO_AUTO_PROVISION`` is off and no admin has invited them.
    """
    try:
        identity = await auth_service.verify_azure_identity(body.token)

        # Resolve the local account row FIRST — it is the source of roles and
        # of the is_active / tombstone lifecycle shared with password users.
        db_user = (
            await db.execute(select(DBUser).where(DBUser.id == identity["id"]))
        ).scalar_one_or_none()
        if db_user is None and identity["email"]:
            # An admin may have invited this person by email before their
            # first SSO login; adopt that row rather than creating a second.
            db_user = (
                await db.execute(
                    select(DBUser).where(func.lower(DBUser.email) == identity["email"].lower())
                )
            ).scalar_one_or_none()

        if db_user is not None:
            if not db_user.is_active:
                raise HTTPException(status_code=403, detail="Account is disabled")
            db_user.last_login = datetime.now(UTC).replace(tzinfo=None)
            await db.commit()
        else:
            if not settings.azure_sso_auto_provision:
                await audit_service.log_event(
                    event_type=AuditEventType.LOGIN_FAILURE,
                    user_email=identity["email"],
                    ip_address=get_client_ip(request),
                    details={"method": "azure_ad", "reason": "not_provisioned"},
                    success=False,
                )
                raise HTTPException(
                    status_code=403,
                    detail="No CaseCite account exists for this identity. "
                    "Ask an administrator to invite you.",
                )
            db_user = DBUser(
                id=identity["id"],
                email=identity["email"],
                name=identity["name"],
                password_hash=None,  # SSO account — no local password
                roles=[_azure_default_role().value],
                email_verified=True,
                is_active=True,
                password_changed_at=datetime.now(UTC).replace(tzinfo=None),
                last_login=datetime.now(UTC).replace(tzinfo=None),
            )
            db.add(db_user)
            await db.commit()
            await audit_service.log_event(
                event_type=AuditEventType.USER_CREATE,
                user_id=db_user.id,
                user_email=db_user.email,
                ip_address=get_client_ip(request),
                details={"method": "azure_ad_auto_provision", "roles": db_user.roles},
            )

        user = User(
            id=db_user.id,
            email=db_user.email,
            name=db_user.name or "",
            roles=[UserRole(r) for r in (db_user.roles or [UserRole.VIEWER.value])],
            azure_oid=identity["azure_oid"],
            tenant_id=identity["tenant_id"],
            mfa_enabled=True,  # Azure AD enforces its own MFA policy
            last_login=datetime.now(UTC).replace(tzinfo=None),
        )
        result = await auth_service.issue_azure_login(user, request)

        # Create session
        session_manager.create_session(
            user_id=user.id,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
            jti=auth_service.verify_token(result["access_token"]).jti,
        )

        _set_auth_cookies(request, response, result["access_token"], result["refresh_token"])

        return LoginResponse(
            access_token=result["access_token"],
            expires_in=int(result["expires_in"]),
            user=result["user"],
        )

    except HTTPException:
        raise
    except (ValueError, KeyError, OSError, RuntimeError) as e:
        await audit_service.log_event(
            event_type=AuditEventType.LOGIN_FAILURE,
            ip_address=get_client_ip(request),
            details={"error": str(e), "method": "azure_ad"},
            success=False,
        )
        raise HTTPException(status_code=401, detail="Authentication failed. Please try again.")


def _azure_default_role() -> UserRole:
    """Role for a first-time SSO user. Misconfiguration fails safe to viewer."""
    configured = (settings.azure_sso_default_role or "viewer").strip().lower()
    try:
        role = UserRole(configured)
    except ValueError:
        logger.warning(
            "AZURE_SSO_DEFAULT_ROLE=%r is not a valid role; provisioning as viewer", configured
        )
        return UserRole.VIEWER
    if role is UserRole.ADMIN:
        # Never hand out admin to anyone who can merely authenticate to the tenant.
        logger.warning("AZURE_SSO_DEFAULT_ROLE=admin is refused; provisioning as viewer")
        return UserRole.VIEWER
    return role


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenRefreshResponse:
    """Refresh an access token using the httpOnly refresh-token cookie.

    The refresh token is never accepted from the request body — only from the
    httpOnly cookie set during login.  This eliminates token exposure to
    JavaScript and browser extensions.
    """
    try:
        raw_token = request.cookies.get("refresh_token")
        if not raw_token:
            raise HTTPException(status_code=401, detail="No refresh token provided")

        # Verify refresh token
        token_data = auth_service.verify_token(raw_token)

        # Enforce refresh token type — reject access tokens
        if token_data.token_type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        # Verify user still exists and is active in the database
        result = await db.execute(select(DBUser).where(DBUser.id == token_data.user_id))
        db_user = result.scalar_one_or_none()
        if not db_user or not getattr(db_user, "is_active", True):
            raise HTTPException(status_code=401, detail="Account disabled or deleted")

        # Reject refresh tokens issued before the last password change so a reset
        # invalidates outstanding refresh tokens too (not just access tokens).
        from app.services.auth import _token_predates_password_change

        pwc = getattr(db_user, "password_changed_at", None)
        if pwc is not None and _token_predates_password_change(token_data.iat, pwc):
            raise HTTPException(status_code=401, detail="Session expired, please sign in again")

        # Create user object from DB (authoritative source) instead of token claims
        user = User(
            id=db_user.id,
            email=db_user.email,
            name=db_user.name or "",
            roles=[UserRole(r) for r in (db_user.roles or ["attorney"])],
        )

        # Rotate the refresh token: revoke the presented one and mint a fresh
        # pair. This makes each refresh token single-use, so a stolen refresh
        # token is good for at most one refresh and any later replay of it is
        # rejected as revoked (verify_token above 401s on a revoked jti) — the
        # signal that the legitimate client and an attacker are both using it.
        auth_service.revoke_token(token_data.jti)

        access_token = auth_service.create_access_token(user)
        new_refresh_token = auth_service.create_refresh_token(user)

        # Register a session for the new access token so validate_session() accepts it
        new_token_data = auth_service.verify_token(access_token)
        session_manager.create_session(
            user_id=user.id,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
            jti=new_token_data.jti,
        )

        await audit_service.log_event(
            event_type=AuditEventType.TOKEN_REFRESH,
            user_id=user.id,
            user_email=user.email,
            ip_address=get_client_ip(request),
        )

        # Re-set BOTH cookies: new access token and the rotated refresh token.
        _set_auth_cookies(request, response, access_token, new_refresh_token)

        return {
            "access_token": access_token,
            "token_type": "bearer",  # nosec B105 - OAuth2 token type, not a password
            "expires_in": int(auth_service.access_token_expire.total_seconds()),
        }

    except HTTPException:
        raise
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.post("/logout", response_model=StatusResponse)
async def logout(
    request: Request, response: Response, current_user: TokenData = Depends(get_current_user)
) -> StatusResponse:
    """Logout and invalidate current session."""
    # Revoke the access token
    auth_service.revoke_token(current_user.jti)

    # Also revoke the refresh token from the cookie so it can't mint new access
    # tokens after logout (the access-token JTI alone doesn't cover it).
    raw_refresh = request.cookies.get("refresh_token")
    if raw_refresh:
        try:
            refresh_data = auth_service.verify_token(raw_refresh)
            if refresh_data.token_type == "refresh":
                auth_service.revoke_token(refresh_data.jti)
        except (JWTError, ValueError, KeyError):
            pass  # already invalid/expired — nothing to revoke

    # Terminate session
    session_manager.terminate_session(current_user.user_id, current_user.jti)

    # Clear httpOnly auth cookies
    _clear_auth_cookies(response)

    await audit_service.log_event(
        event_type=AuditEventType.LOGOUT,
        user_id=current_user.user_id,
        user_email=current_user.email,
        ip_address=get_client_ip(request),
    )

    return {"status": "logged_out"}


@router.post("/logout/all", response_model=StatusResponse)
async def logout_all_sessions(
    request: Request, response: Response, current_user: TokenData = Depends(get_current_user)
) -> StatusResponse:
    """Logout from all sessions."""
    # Revoke all JWT tokens for this user's active sessions
    for session in session_manager.get_active_sessions_raw(current_user.user_id):
        auth_service.revoke_token(session["jti"])

    session_manager.terminate_all_sessions(current_user.user_id)

    # Clear httpOnly auth cookies for the current session
    _clear_auth_cookies(response)

    await audit_service.log_event(
        event_type=AuditEventType.LOGOUT,
        user_id=current_user.user_id,
        user_email=current_user.email,
        details={"scope": "all_sessions"},
        ip_address=get_client_ip(request),
    )

    return {"status": "all_sessions_terminated"}


@router.get("/sessions", response_model=SessionsResponse)
async def get_sessions(current_user: TokenData = Depends(get_current_user)) -> SessionsResponse:
    """Get all active sessions for current user."""
    sessions = session_manager.get_active_sessions(current_user.user_id)
    return {"sessions": sessions}


@router.get("/me", response_model=CurrentUserResponse)
async def get_current_user_info(
    current_user: TokenData = Depends(get_current_user),
) -> CurrentUserResponse:
    """Get current user information."""
    return {
        "id": current_user.user_id,
        "email": current_user.email,
        "roles": current_user.roles,
        "token_expires": current_user.exp.isoformat(),
    }


@router.get("/azure/config", response_model=AzureConfigResponse)
async def get_azure_config() -> AzureConfigResponse:
    """
    Get Azure AD configuration for frontend.

    Frontend uses this to initiate Azure login.
    """
    from app.config import settings

    if not settings.microsoft_client_id:
        raise HTTPException(status_code=503, detail="Azure AD not configured")

    tenant = settings.microsoft_tenant_id or "common"

    return {
        "authority": f"https://login.microsoftonline.com/{tenant}",
        "client_id": settings.microsoft_client_id,
        "redirect_uri": settings.microsoft_redirect_uri,
        "scopes": ["User.Read", "openid", "profile", "email"],
    }


# ==================== Password Change / Reset Endpoints ====================


@router.post("/change-password", response_model=StatusResponse)
async def change_password(
    request: Request,
    response: Response,
    body: ChangePasswordRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatusResponse:
    """Change the signed-in user's password after verifying the current one.

    Works with no email/SMTP configured (the reset flow requires SendGrid).
    Verifies the current password, enforces the password policy, stamps
    password_changed_at (which invalidates every outstanding access/refresh
    token), and tears down all other sessions.
    """
    from app.services.password_policy import validate_password
    from app.services.passwords import hash_password, verify_password

    result = await db.execute(select(DBUser).where(DBUser.id == current_user.user_id))
    db_user = result.scalar_one_or_none()
    if not db_user or not db_user.password_hash:
        raise HTTPException(
            status_code=400, detail="Password change is not available for this account."
        )

    if not await asyncio.to_thread(verify_password, body.current_password, db_user.password_hash):
        await audit_service.log_event(
            event_type=AuditEventType.PASSWORD_CHANGE,
            user_id=db_user.id,
            user_email=db_user.email,
            details={"reason": "wrong_current_password"},
            ip_address=get_client_ip(request),
            success=False,
        )
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    pw_errors = validate_password(body.new_password)
    if pw_errors:
        raise HTTPException(status_code=400, detail="; ".join(pw_errors))

    db_user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
    db_user.password_changed_at = datetime.now(UTC).replace(tzinfo=None)

    # Revoke every existing session/token; the caller must sign in again.
    for _session in session_manager.get_active_sessions_raw(db_user.id):
        auth_service.revoke_token(_session["jti"])
    session_manager.terminate_all_sessions(db_user.id)
    await db.commit()

    _clear_auth_cookies(response)

    await audit_service.log_event(
        event_type=AuditEventType.PASSWORD_CHANGE,
        user_id=db_user.id,
        user_email=db_user.email,
        ip_address=get_client_ip(request),
    )
    return {"status": "password_changed"}


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Request a password reset email.

    Always returns success to prevent email enumeration.
    """
    import logging

    from app.config import settings
    from app.services.auth import password_reset_service

    logger = logging.getLogger(__name__)

    email = body.email.lower().strip()

    # Check if user exists before generating a token to prevent token storage DoS
    # (response is always the same to prevent email enumeration)
    user_exists = False
    try:
        result = await db.execute(select(DBUser.id).where(DBUser.email == email))
        user_exists = result.scalar_one_or_none() is not None
    except (ValueError, KeyError, OSError, RuntimeError):
        pass

    if not user_exists:
        # Log and return same response to prevent enumeration
        await audit_service.log_event(
            event_type=AuditEventType.SECURITY_ALERT,
            user_email=email,
            ip_address=get_client_ip(request),
            details={"action": "password_reset_requested", "user_found": False},
        )
        return {"message": "If an account exists with this email, you will receive a reset link."}

    # Generate reset token only for existing users
    token = password_reset_service.generate_reset_token(email)

    # Build reset URL using configured frontend URL (not untrusted Origin header)
    if settings.frontend_url:
        base_url = settings.frontend_url.rstrip("/")
    elif settings.debug:
        # Dev fallback: use Origin header only in debug mode
        base_url = request.headers.get("origin", "http://localhost:3000")
    else:
        # Production requires FRONTEND_URL to be configured
        logger.error("FRONTEND_URL not configured — cannot send password reset email")
        # Still return success to prevent email enumeration
        await audit_service.log_event(
            event_type=AuditEventType.SECURITY_ALERT,
            user_email=email,
            ip_address=get_client_ip(request),
            details={"action": "password_reset_requested", "error": "frontend_url_not_configured"},
        )
        return {"message": "If an account exists with this email, you will receive a reset link."}
    reset_url = f"{base_url}/reset-password?token={token}"

    # Send email via the email service (SendGrid's sync HTTP runs off the loop)
    if settings.debug:
        # Development only - log that a token was generated (never log the token itself)
        logger.info("[DEBUG] Password reset token generated")
        logger.info("[DEBUG] Reset URL generated")
    else:
        from app.services.email import send_password_reset_email

        await send_password_reset_email(to_email=email, reset_url=reset_url)

    await audit_service.log_event(
        event_type=AuditEventType.PASSWORD_RESET_REQUEST,
        user_email=email,
        ip_address=get_client_ip(request),
        details={"action": "password_reset_requested"},
    )

    # Always return success to prevent email enumeration
    return {"message": "If an account exists with this email, you will receive a reset link."}


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Reset password using a valid token.
    """
    from app.services.auth import password_reset_service
    from app.services.passwords import hash_password

    # Verify the token
    email = password_reset_service.verify_reset_token(body.token)

    if not email:
        await audit_service.log_event(
            event_type=AuditEventType.SECURITY_ALERT,
            ip_address=get_client_ip(request),
            details={"action": "invalid_reset_token"},
            success=False,
        )
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Validate password strength
    from app.services.password_policy import validate_password

    password_errors = validate_password(body.new_password)
    if password_errors:
        raise HTTPException(status_code=400, detail="; ".join(password_errors))

    # Hash the new password
    password_hash = await asyncio.to_thread(hash_password, body.new_password)

    # Update user password in database
    try:
        result = await db.execute(select(DBUser).where(DBUser.email == email))
        user = result.scalar_one_or_none()

        if user:
            user.password_hash = password_hash
            user.password_changed_at = datetime.now(UTC).replace(tzinfo=None)

            # Proactively tear down existing sessions. Outstanding tokens are
            # already rejected via the password_changed_at check in
            # get_current_user / refresh, but clearing sessions keeps state tidy
            # and covers the current worker immediately.
            for _session in session_manager.get_active_sessions_raw(user.id):
                auth_service.revoke_token(_session["jti"])
            session_manager.terminate_all_sessions(user.id)

            # Invalidate the token
            password_reset_service.invalidate_token(body.token)

            await audit_service.log_event(
                event_type=AuditEventType.PASSWORD_RESET_COMPLETE,
                user_id=user.id,
                user_email=email,
                ip_address=get_client_ip(request),
                details={"action": "password_reset_success"},
            )

            return {"message": "Password reset successfully. You can now log in."}
        else:
            raise HTTPException(status_code=404, detail="User not found")

    except HTTPException:
        raise
    except (ValueError, KeyError, OSError, RuntimeError) as e:
        await audit_service.log_event(
            event_type=AuditEventType.SECURITY_ALERT,
            user_email=email,
            ip_address=get_client_ip(request),
            details={"action": "password_reset_failed", "error": str(e)},
            success=False,
        )
        raise HTTPException(status_code=500, detail="Failed to reset password")


@router.post("/verify-reset-token", response_model=ResetTokenValidationResponse)
async def verify_reset_token(body: VerifyResetTokenRequest) -> ResetTokenValidationResponse:
    """
    Verify if a reset token is valid (frontend can check before showing form).
    """
    from app.services.auth import password_reset_service

    email = password_reset_service.verify_reset_token(body.token)
    return {"valid": email is not None}
