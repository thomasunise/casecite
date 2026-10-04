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
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from jwt.exceptions import PyJWTError as JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.csrf import cookie_secure
from app.middleware.security import account_lockout, session_manager
from app.models.db_models import User as DBUser
from app.models.responses.auth import (
    AzureConfigResponse,
    CurrentUserResponse,
    LoginResponse,
    ResetTokenValidationResponse,
    SessionsResponse,
    TokenRefreshResponse,
    UserInfo,
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
from app.services.auth import (
    TokenData,
    User,
    UserRole,
    _token_predates_password_change,
    auth_service,
    get_current_user,
    mfa_enrollment_required,
    password_reset_service,
)
from app.utils.ip_resolution import get_client_ip

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = logging.getLogger(__name__)

# Hardcoded account for the dev-only login (POST /auth/demo/login, DEBUG=true only).
DEV_ACCOUNT_EMAIL = "dev@localhost"

_RESET_REQUESTED_MESSAGE = "If an account exists with this email, you will receive a reset link."

# Serializes "is this the first account?" with the insert that answers it, so
# two simultaneous first registrations cannot both be granted admin. The app
# runs as a single process (enforced at startup), so a process lock suffices.
_registration_lock = asyncio.Lock()

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
    # Always Secure in production; scheme-dependent only in local development.
    secure = cookie_secure(request)
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


def start_session(request: Request, response: Response, user: User) -> str:
    """Begin a sign-in: mint the token pair, register the session, set cookies.

    The access and refresh tokens share a session id (``sid``); /auth/refresh
    continues that same session rather than opening a new one, which is what
    makes the absolute lifetime, idle timeout and concurrent-session cap hold
    across refreshes. Returns the access token.
    """
    session_id = uuid.uuid4().hex
    access_token = auth_service.create_access_token(user, session_id=session_id)
    refresh_token = auth_service.create_refresh_token(user, session_id=session_id)
    session_manager.create_session(
        user_id=user.id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        jti=auth_service.verify_token(access_token).jti,
        session_id=session_id,
    )
    _set_auth_cookies(request, response, access_token, refresh_token)
    return access_token


def user_from_row(db_user: DBUser, default_role: str = "attorney") -> User:
    """Token subject built from the database row (the authoritative source)."""
    return User(
        id=db_user.id,
        email=db_user.email,
        name=db_user.name or "",
        roles=[UserRole(r) for r in (db_user.roles or [default_role])],
        last_login=datetime.now(UTC),
        token_version=int(db_user.token_version or 0),
    )


def user_info(user: User, db_user: DBUser | None = None) -> UserInfo:
    """The user object returned by login-type endpoints."""
    mfa_enabled = bool(db_user.mfa_enabled) if db_user is not None else False
    has_password = db_user is not None and db_user.password_hash is not None
    return UserInfo(
        id=user.id,
        email=user.email,
        name=user.name,
        roles=[r.value for r in user.roles],
        mfa_enabled=mfa_enabled,
        must_change_password=bool(db_user.must_change_password) if db_user is not None else False,
        mfa_enrollment_required=mfa_enrollment_required(mfa_enabled, has_password),
    )


async def invalidate_all_user_tokens(db: AsyncSession, db_user: DBUser) -> int:
    """Kill every token of a user on every device; returns live sessions ended.

    Bumps ``users.token_version`` (durable: outstanding access AND refresh
    tokens carry the old version and are rejected from now on), commits, then
    revokes and drops the live sessions.
    """
    db_user.token_version = int(db_user.token_version or 0) + 1
    await db.commit()
    return auth_service.revoke_user_sessions(db_user.id)


@router.post("/demo/login", response_model=LoginResponse)
async def dev_login(request: Request, response: Response, body: DemoLoginRequest) -> LoginResponse:
    """
    DEV LOGIN (DEBUG=true only).

    Signs in a hardcoded local-development account (DEV_ACCOUNT_EMAIL /
    password "demo") without touching the users table. Refuses (403) unless
    DEBUG=true, so it can never be a bypass on a production instance.
    """
    if not settings.debug:
        await audit_service.log_event(
            event_type=AuditEventType.LOGIN_FAILURE,
            user_email=body.email,
            details={"method": "dev", "reason": "dev_login_disabled"},
            ip_address=get_client_ip(request),
            success=False,
        )
        raise HTTPException(status_code=403, detail="Dev login is disabled")

    logger.warning("DEV LOGIN (DEBUG=true only) used from IP %s", get_client_ip(request))

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

    access_token = start_session(request, response, user)

    await audit_service.log_event(
        event_type=AuditEventType.LOGIN_SUCCESS,
        user_id=user.id,
        user_email=user.email,
        details={"method": "demo"},
        ip_address=get_client_ip(request),
    )

    return LoginResponse(
        access_token=access_token,
        expires_in=int(auth_service.access_token_expire.total_seconds()),
        user=user_info(user),
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

    The first account on a fresh install becomes the admin. In production that
    first registration requires REGISTRATION_BOOTSTRAP_TOKEN, so whoever
    reaches a new instance first cannot simply claim it.
    """
    from app.services.password_policy import validate_password
    from app.services.passwords import hash_password

    email = body.email.lower().strip()

    async with _registration_lock:
        # The very first account on a fresh install becomes the admin so there is
        # always someone who can manage users and instance settings.
        user_count = (await db.execute(select(func.count()).select_from(DBUser))).scalar_one()

        if user_count == 0:
            # Bootstrapping the first (admin) account requires the operator's
            # bootstrap token, so an attacker who reaches a fresh instance first
            # cannot seize the admin slot. Local development (DEBUG) may omit it.
            if settings.registration_bootstrap_token:
                provided = (body.bootstrap_token or "").strip()
                if not secrets.compare_digest(provided, settings.registration_bootstrap_token):
                    await audit_service.log_event(
                        event_type=AuditEventType.SECURITY_ALERT,
                        user_email=email,
                        details={"reason": "invalid_bootstrap_token"},
                        ip_address=get_client_ip(request),
                    )
                    raise HTTPException(
                        status_code=403, detail="A valid bootstrap token is required."
                    )
            elif not settings.debug:
                await audit_service.log_event(
                    event_type=AuditEventType.SECURITY_ALERT,
                    user_email=email,
                    details={"reason": "bootstrap_token_not_configured"},
                    ip_address=get_client_ip(request),
                )
                raise HTTPException(
                    status_code=403,
                    detail="The first account cannot be created until the operator sets "
                    "REGISTRATION_BOOTSTRAP_TOKEN on the server. Set it, restart, and "
                    "register with that value as the bootstrap token.",
                )
        else:
            # Subsequent registrations are only allowed when registration is
            # explicitly enabled (or in local development). This prevents anyone
            # reachable on the network from self-provisioning a full-access
            # account. Checked BEFORE the duplicate-email lookup so a closed
            # instance does not reveal which addresses have accounts.
            if not (settings.allow_registration or settings.debug):
                raise HTTPException(
                    status_code=403,
                    detail="Self-service registration is disabled. Ask an administrator "
                    "for an invite.",
                )

        existing = await db.execute(select(DBUser).where(DBUser.email == email))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409, detail="An account with this email already exists."
            )

        pw_errors = validate_password(body.password)
        if pw_errors:
            raise HTTPException(status_code=400, detail="; ".join(pw_errors))

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
            last_login=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

    user = user_from_row(db_user)
    access_token = start_session(request, response, user)

    await audit_service.log_event(
        event_type=AuditEventType.USER_CREATE,
        user_id=user.id,
        user_email=user.email,
        details={"method": "self_hosted_register", "roles": initial_roles},
        ip_address=get_client_ip(request),
    )

    return LoginResponse(
        access_token=access_token,
        expires_in=int(auth_service.access_token_expire.total_seconds()),
        user=user_info(user, db_user),
    )


@router.post("/login", response_model=LoginResponse)
async def email_login(
    request: Request,
    response: Response,
    body: EmailLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Login with email and password.

    When the account has MFA enabled the response is
    ``{"mfa_required": true, "mfa_token": ...}`` instead of tokens;
    POST /auth/mfa/verify completes the sign-in.
    """
    from app.services.passwords import verify_password

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
            await audit_service.log_event(
                event_type=AuditEventType.LOGIN_FAILURE,
                user_id=db_user.id,
                user_email=db_user.email,
                details={"method": "email", "reason": "account_disabled"},
                ip_address=get_client_ip(request),
                success=False,
            )
            raise HTTPException(status_code=403, detail="Account is disabled")

        # If MFA is enabled, the password is only the first factor. Return a
        # short-lived challenge instead of tokens; /auth/mfa/verify completes it.
        if db_user.mfa_enabled:
            from app.services import mfa as mfa_service

            # The lockout counter is deliberately NOT cleared here: it also
            # counts failed second-factor attempts, and clearing it on a correct
            # password would let someone who knows the password guess TOTP codes
            # forever (4 wrong codes, re-enter the password, repeat). It is
            # cleared only when the whole sign-in succeeds (/auth/mfa/verify).
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
        db_user.last_login = datetime.now(UTC).replace(tzinfo=None)
        await db.commit()
        user = user_from_row(db_user)
        access_token = start_session(request, response, user)

        # Clear account lockout on successful login
        account_lockout.clear_account_lockout(body.email)

        await audit_service.log_event(
            event_type=AuditEventType.LOGIN_SUCCESS,
            user_id=user.id,
            user_email=user.email,
            details={"method": "email"},
            ip_address=get_client_ip(request),
        )

        # Refresh token is delivered only in the httpOnly cookie, not the body.
        return LoginResponse(
            access_token=access_token,
            expires_in=int(auth_service.access_token_expire.total_seconds()),
            user=user_info(user, db_user),
        )
    except HTTPException:
        raise
    except (ValueError, KeyError, OSError, RuntimeError) as e:
        logger.debug(f"Login error details: {e}", exc_info=True)
        logger.error("Login failed for user")
        raise HTTPException(status_code=500, detail="Login failed. Please try again.")


def _may_link_by_email(row: DBUser) -> bool:
    """Whether an existing local row may be attached to an SSO identity by email.

    The token's email claim is mutable and not verified by Microsoft, so a
    matching address is only accepted for a row that nobody has ever used
    locally and that carries nothing worth stealing: not an admin, no MFA,
    not already linked to another identity, and either no password at all or
    only an admin-issued temporary password that was never used to sign in.
    """
    roles = row.roles if isinstance(row.roles, list) else []
    if UserRole.ADMIN.value in roles or row.mfa_enabled or row.azure_oid:
        return False
    if row.password_hash is None:
        return True
    return bool(row.must_change_password) and row.last_login is None


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

    Accounts are matched on the immutable Azure object id. An existing local
    row is attached by email only on its first SSO login and only when it is
    an unused, non-admin invite (see _may_link_by_email); the object id is
    then stored so every later login matches on it.
    """
    try:
        identity = await auth_service.verify_azure_identity(body.token)
        oid = identity["azure_oid"] or identity["id"]

        # Resolve the local account row FIRST — it is the source of roles and
        # of the is_active / tombstone lifecycle shared with password users.
        db_user = (
            await db.execute(select(DBUser).where(DBUser.azure_oid == oid))
        ).scalar_one_or_none()
        if db_user is None:
            db_user = (
                await db.execute(select(DBUser).where(DBUser.id == identity["id"]))
            ).scalar_one_or_none()
        if db_user is None and identity["email"]:
            # An admin may have invited this person by email before their
            # first SSO login; adopt that row rather than creating a second —
            # but never take over an account that is in local use.
            candidate = (
                await db.execute(
                    select(DBUser).where(func.lower(DBUser.email) == identity["email"].lower())
                )
            ).scalar_one_or_none()
            if candidate is not None:
                if not _may_link_by_email(candidate):
                    await audit_service.log_event(
                        event_type=AuditEventType.SECURITY_ALERT,
                        user_id=candidate.id,
                        user_email=candidate.email,
                        ip_address=get_client_ip(request),
                        details={"method": "azure_ad", "reason": "sso_email_link_refused"},
                        success=False,
                    )
                    raise HTTPException(
                        status_code=403,
                        detail="An account with this email already exists and cannot be "
                        "linked to single sign-on automatically. Ask an administrator.",
                    )
                # From now on this row is an SSO account: the temporary password
                # (known to the inviting admin) stops being a way in.
                candidate.password_hash = None
                candidate.must_change_password = False
                db_user = candidate

        if db_user is not None:
            if not db_user.is_active:
                await audit_service.log_event(
                    event_type=AuditEventType.LOGIN_FAILURE,
                    user_id=db_user.id,
                    user_email=db_user.email,
                    ip_address=get_client_ip(request),
                    details={"method": "azure_ad", "reason": "account_disabled"},
                    success=False,
                )
                raise HTTPException(status_code=403, detail="Account is disabled")
            if not db_user.azure_oid:
                db_user.azure_oid = oid
                db_user.tenant_id = identity["tenant_id"]
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
                azure_oid=oid,
                tenant_id=identity["tenant_id"],
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
            token_version=int(db_user.token_version or 0),
        )
        session_id = uuid.uuid4().hex
        result = await auth_service.issue_azure_login(user, request, session_id=session_id)

        session_manager.create_session(
            user_id=user.id,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
            jti=auth_service.verify_token(result["access_token"]).jti,
            session_id=session_id,
        )

        _set_auth_cookies(request, response, result["access_token"], result["refresh_token"])

        return LoginResponse(
            access_token=result["access_token"],
            expires_in=int(result["expires_in"]),
            user=user_info(user, db_user),
        )

    except HTTPException:
        raise
    except (ValueError, KeyError, OSError, RuntimeError) as e:
        await audit_service.log_event(
            event_type=AuditEventType.LOGIN_FAILURE,
            ip_address=get_client_ip(request),
            details={"error_type": type(e).__name__, "method": "azure_ad"},
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

    A refresh continues the sign-in session the token is bound to: it never
    extends the session's absolute lifetime, and it is refused once that
    session has ended (logout, "log out everywhere", idle timeout, eviction by
    the concurrent-session cap, admin force sign-out).
    """
    try:
        raw_token = request.cookies.get("refresh_token")
        if not raw_token:
            raise HTTPException(status_code=401, detail="No refresh token provided")

        # Verify signature/expiry. Revocation is decided below by
        # claim_refresh_token, which also detects replay of a rotated token.
        token_data = auth_service.verify_token(raw_token, check_revocation=False)

        # Enforce refresh token type — reject access tokens
        if token_data.token_type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        # Verify user still exists and is active in the database
        result = await db.execute(select(DBUser).where(DBUser.id == token_data.user_id))
        db_user = result.scalar_one_or_none()
        if not db_user or not db_user.is_active:
            raise HTTPException(status_code=401, detail="Account disabled or deleted")

        # Reject refresh tokens issued before the last password change so a reset
        # invalidates outstanding refresh tokens too (not just access tokens).
        pwc = db_user.password_changed_at
        if pwc is not None and _token_predates_password_change(token_data.iat, pwc):
            raise HTTPException(status_code=401, detail="Session expired, please sign in again")

        # Reject tokens minted before "log out everywhere" / force sign-out.
        if token_data.token_version != int(db_user.token_version or 0):
            raise HTTPException(status_code=401, detail="Session expired, please sign in again")

        # Rotate: spend the presented refresh token (atomically) and mint a
        # fresh pair, so each refresh token is single-use.
        claim = auth_service.claim_refresh_token(token_data.jti)
        if claim == "reused":
            # A refresh token that was already rotated is being presented again:
            # the legitimate client and someone else both hold it. Which of them
            # is asking is unknowable, so end every session of this user.
            ended = await invalidate_all_user_tokens(db, db_user)
            await audit_service.log_event(
                event_type=AuditEventType.SESSION_HIJACK_ATTEMPT,
                user_id=db_user.id,
                user_email=db_user.email,
                ip_address=get_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                details={"reason": "refresh_token_reuse", "sessions_revoked": ended},
                success=False,
            )
            raise HTTPException(status_code=401, detail="Session expired, please sign in again")
        if claim != "ok":
            raise HTTPException(status_code=401, detail="Token has been revoked")

        # Create user object from DB (authoritative source) instead of token claims
        user = user_from_row(db_user)

        access_token = auth_service.create_access_token(user, session_id=token_data.session_id)
        replaced_jti = session_manager.rotate_session(
            user.id,
            token_data.session_id,
            auth_service.verify_token(access_token).jti,
            ip_address=get_client_ip(request),
        )
        if replaced_jti is None:
            # No live session behind this refresh token: it was signed out,
            # evicted, idle too long, or is past its absolute lifetime.
            raise HTTPException(status_code=401, detail="Session expired, please sign in again")
        new_refresh_token = auth_service.create_refresh_token(
            user, session_id=token_data.session_id
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
        except (HTTPException, JWTError, ValueError, KeyError):
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
    request: Request,
    response: Response,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatusResponse:
    """Logout from all sessions on every device.

    Ends every live session AND invalidates every outstanding access and
    refresh token of the account (users.token_version is bumped), so a refresh
    cookie on another device can no longer mint a new session.
    """
    db_user = (
        await db.execute(select(DBUser).where(DBUser.id == current_user.user_id))
    ).scalar_one_or_none()
    if db_user is not None:
        ended = await invalidate_all_user_tokens(db, db_user)
    else:
        # No users row (the DEBUG-only dev account): sessions only.
        ended = auth_service.revoke_user_sessions(current_user.user_id)

    # Clear httpOnly auth cookies for the current session
    _clear_auth_cookies(response)

    await audit_service.log_event(
        event_type=AuditEventType.LOGOUT,
        user_id=current_user.user_id,
        user_email=current_user.email,
        details={"scope": "all_sessions", "sessions_revoked": ended},
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
    db: AsyncSession = Depends(get_db),
) -> CurrentUserResponse:
    """Get current user information.

    ``must_change_password`` and ``mfa_enrollment_required`` tell the client
    which step the account still has to complete; while either is true the
    rest of the API answers 403 with the matching ``code``.
    """
    db_user = (
        await db.execute(select(DBUser).where(DBUser.id == current_user.user_id))
    ).scalar_one_or_none()
    mfa_enabled = bool(db_user.mfa_enabled) if db_user is not None else False
    has_password = db_user is not None and db_user.password_hash is not None
    return {
        "id": current_user.user_id,
        "email": current_user.email,
        "name": (db_user.name or "") if db_user is not None else "",
        "roles": current_user.roles,
        "token_expires": current_user.exp.isoformat(),
        "mfa_enabled": mfa_enabled,
        "must_change_password": bool(db_user.must_change_password)
        if db_user is not None
        else False,
        "mfa_enrollment_required": mfa_enrollment_required(mfa_enabled, has_password),
    }


@router.get("/azure/config", response_model=AzureConfigResponse)
async def get_azure_config() -> AzureConfigResponse:
    """
    Get Azure AD configuration for frontend.

    Frontend uses this to initiate Azure login.
    """
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
    token), clears the must-change-password flag set on invite, and tears down
    every session — the caller signs in again with the new password.
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

    if secrets.compare_digest(body.new_password, body.current_password):
        raise HTTPException(
            status_code=400, detail="The new password must be different from the current one."
        )

    pw_errors = validate_password(body.new_password)
    if pw_errors:
        raise HTTPException(status_code=400, detail="; ".join(pw_errors))

    db_user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
    db_user.password_changed_at = datetime.now(UTC).replace(tzinfo=None)
    db_user.must_change_password = False
    await db.commit()

    # Revoke every existing session/token; the caller must sign in again.
    auth_service.revoke_user_sessions(db_user.id)

    _clear_auth_cookies(response)

    await audit_service.log_event(
        event_type=AuditEventType.PASSWORD_CHANGE,
        user_id=db_user.id,
        user_email=db_user.email,
        ip_address=get_client_ip(request),
    )
    return {"status": "password_changed"}


async def _deliver_reset_link(email: str, reset_url: str) -> None:
    """Hand the reset link to the user (runs after the response is sent)."""
    if settings.debug and not settings.sendgrid_api_key:
        # Local development has no mail transport; without this the reset flow
        # cannot be completed at all. Never reached in production (DEBUG=false).
        logger.warning("[DEBUG ONLY] Password reset link for %s: %s", email, reset_url)
        return

    from app.services.email import send_password_reset_email

    await send_password_reset_email(to_email=email, reset_url=reset_url)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Request a password reset email.

    Always returns success to prevent email enumeration. The email itself is
    sent after the response (background task), so the response time does not
    depend on whether an account exists or on the mail provider.
    """
    email = body.email.lower().strip()

    # Only accounts that HAVE a local password can reset it. An SSO-only account
    # (password_hash is NULL) is treated exactly like an unknown address:
    # resetting it would create a password path around the identity provider.
    resettable = False
    try:
        result = await db.execute(
            select(DBUser.password_hash, DBUser.is_active).where(DBUser.email == email)
        )
        row = result.one_or_none()
        resettable = row is not None and row[0] is not None and bool(row[1])
    except (ValueError, KeyError, OSError, RuntimeError):
        pass

    if not resettable:
        # Log and return same response to prevent enumeration
        await audit_service.log_event(
            event_type=AuditEventType.SECURITY_ALERT,
            user_email=email,
            ip_address=get_client_ip(request),
            details={"action": "password_reset_requested", "user_found": False},
        )
        return {"message": _RESET_REQUESTED_MESSAGE}

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
        return {"message": _RESET_REQUESTED_MESSAGE}

    # Generate reset token only for resettable accounts (prevents token-storage DoS)
    token = password_reset_service.generate_reset_token(email)
    reset_url = f"{base_url}/reset-password?token={token}"

    background_tasks.add_task(_deliver_reset_link, email, reset_url)

    await audit_service.log_event(
        event_type=AuditEventType.PASSWORD_RESET_REQUEST,
        user_email=email,
        ip_address=get_client_ip(request),
        details={"action": "password_reset_requested"},
    )

    # Always return success to prevent email enumeration
    return {"message": _RESET_REQUESTED_MESSAGE}


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Reset password using a valid token.
    """
    from app.services.password_policy import validate_password
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
    password_errors = validate_password(body.new_password)
    if password_errors:
        raise HTTPException(status_code=400, detail="; ".join(password_errors))

    # Hash the new password
    password_hash = await asyncio.to_thread(hash_password, body.new_password)

    # Update user password in database
    try:
        result = await db.execute(select(DBUser).where(DBUser.email == email))
        user = result.scalar_one_or_none()

        # An SSO-only account must never acquire a local password this way, and
        # a deactivated account has nothing to reset. Both look like a bad token.
        if user is None or user.password_hash is None or not user.is_active:
            password_reset_service.invalidate_token(body.token)
            await audit_service.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                user_email=email,
                ip_address=get_client_ip(request),
                details={"action": "password_reset_refused"},
                success=False,
            )
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")

        user.password_hash = password_hash
        user.password_changed_at = datetime.now(UTC).replace(tzinfo=None)
        user.must_change_password = False
        await db.commit()

        # Proactively tear down existing sessions. Outstanding tokens are
        # already rejected via the password_changed_at check in
        # get_current_user / refresh, but clearing sessions keeps state tidy
        # and covers the current worker immediately.
        auth_service.revoke_user_sessions(user.id)

        # Invalidate the token
        password_reset_service.invalidate_token(body.token)

        # The owner of the mailbox has proven control: lift any login lockout.
        account_lockout.clear_account_lockout(email)

        await audit_service.log_event(
            event_type=AuditEventType.PASSWORD_RESET_COMPLETE,
            user_id=user.id,
            user_email=email,
            ip_address=get_client_ip(request),
            details={"action": "password_reset_success"},
        )

        return {"message": "Password reset successfully. You can now log in."}

    except HTTPException:
        raise
    except (ValueError, KeyError, OSError, RuntimeError) as e:
        await audit_service.log_event(
            event_type=AuditEventType.SECURITY_ALERT,
            user_email=email,
            ip_address=get_client_ip(request),
            details={"action": "password_reset_failed", "error_type": type(e).__name__},
            success=False,
        )
        raise HTTPException(status_code=500, detail="Failed to reset password")


@router.post("/verify-reset-token", response_model=ResetTokenValidationResponse)
async def verify_reset_token(body: VerifyResetTokenRequest) -> ResetTokenValidationResponse:
    """
    Verify if a reset token is valid (frontend can check before showing form).
    """
    email = password_reset_service.verify_reset_token(body.token)
    return {"valid": email is not None}
