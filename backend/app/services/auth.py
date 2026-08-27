"""
Authentication Service

Supports:
- JWT access/refresh tokens with JTI revocation
- Azure AD token verification (SSO identity only; roles come from the database)
- Role-based access control (RBAC)
- Password reset tokens
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWTError as JWTError
from pydantic import BaseModel, Field

from app.config import settings
from app.redis_utils import RedisError, get_redis
from app.services.audit import AuditEventType, audit_service

logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    ADMIN = "admin"  # Full access
    ATTORNEY = "attorney"  # Full document access
    PARALEGAL = "paralegal"  # Limited access
    VIEWER = "viewer"  # Read-only


class User(BaseModel):
    id: str
    email: str
    name: str
    roles: list[UserRole]
    tenant_id: str | None = None
    azure_oid: str | None = None  # Azure AD Object ID
    mfa_enabled: bool = False
    last_login: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TokenData(BaseModel):
    user_id: str
    email: str
    roles: list[str]
    exp: datetime
    iat: datetime
    jti: str  # JWT ID for revocation
    token_type: str = "access"  # "access" or "refresh"


class AuthService:
    """Authentication and authorization service."""

    def __init__(self):
        # Domain-separated JWT signing key (HKDF from SECRET_KEY), so a leaked
        # token-signing key can't be reversed to the encryption/CSRF keys.
        from app.utils.keys import derive_subkey

        self.secret_key = derive_subkey("jwt-hs256")
        self.algorithm = "HS256"
        self.access_token_expire = timedelta(minutes=settings.access_token_expire_minutes)
        self.refresh_token_expire = timedelta(days=7)

        # Token blacklist - use Redis in production for persistence
        self._revoked_tokens = set()  # Fallback for development
        # User-level tombstones: a deleted user's id is recorded here so any
        # still-unexpired access token is rejected on EVERY worker (via Redis),
        # even though the user's DB row — and its is_active check — is gone.
        self._revoked_users = set()
        self._revocation_file = Path(settings.upload_dir).parent / "revoked_tokens.jsonl"
        self._load_revoked_tokens_from_file()

        if not settings.debug and not get_redis():
            logger.critical(
                "CRITICAL: Redis unavailable in production. Token revocation "
                "will rely on file-based fallback only."
            )

        # Azure AD configuration — require explicit tenant to prevent any-tenant auth
        self.azure_tenant = settings.microsoft_tenant_id
        self.azure_client_id = settings.microsoft_client_id
        if self.azure_client_id and not self.azure_tenant:
            logger.warning(
                "Azure AD client_id configured without tenant_id — SSO disabled for safety. "
                "Set MICROSOFT_TENANT_ID to enable Azure AD SSO."
            )
            self.azure_client_id = None  # Disable SSO rather than accept 'common'

        # Azure AD JWKS cache
        self._jwks_cache = None
        self._jwks_cache_time = None
        self._jwks_cache_ttl = 3600  # 1 hour

    def _load_revoked_tokens_from_file(self):
        """Load unexpired revocations from file on startup."""
        try:
            if not self._revocation_file.exists():
                return
            now = datetime.now(UTC)
            with open(self._revocation_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        expires_at = datetime.fromisoformat(entry["expires_at"])
                        if expires_at > now:
                            self._revoked_tokens.add(entry["jti"])
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
            logger.info(f"Loaded {len(self._revoked_tokens)} revoked tokens from file")
        except OSError as e:
            logger.warning(f"Could not load revoked tokens from file: {e}")

    def _persist_revocation_to_file(self, jti: str):
        """Write revocation to file as secondary backup."""
        try:
            import os
            import stat

            expires_at = datetime.now(UTC) + timedelta(days=7)
            entry = {"jti": jti, "expires_at": expires_at.isoformat()}
            self._revocation_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._revocation_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
            # Restrict file permissions to owner only (0o600)
            try:
                os.chmod(self._revocation_file, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass  # Windows may not support chmod
        except OSError as e:
            logger.error(f"Could not persist token revocation to file: {e}")

    # ==================== JWT Token Management ====================

    def create_access_token(self, user: User) -> str:
        """Create a new access token."""
        import uuid

        now = datetime.now(UTC)
        payload = {
            "sub": user.id,
            "email": user.email,
            "name": user.name,
            "roles": [r.value for r in user.roles],
            "iat": now,
            "exp": now + self.access_token_expire,
            "jti": str(uuid.uuid4()),
            "type": "access",
            "aud": "casecite",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user: User) -> str:
        """Create a new refresh token."""
        import uuid

        now = datetime.now(UTC)
        payload = {
            "sub": user.id,
            "iat": now,
            "exp": now + self.refresh_token_expire,
            "jti": str(uuid.uuid4()),
            "type": "refresh",
            "aud": "casecite",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> TokenData:
        """Verify and decode a token."""
        try:
            payload = jwt.decode(
                token, self.secret_key, algorithms=[self.algorithm], audience="casecite"
            )

            # Check if token is revoked
            jti = payload.get("jti")
            if self._is_token_revoked(jti):
                raise HTTPException(status_code=401, detail="Token has been revoked")

            return TokenData(
                user_id=payload["sub"],
                email=payload.get("email", ""),
                roles=payload.get("roles", []),
                exp=datetime.fromtimestamp(payload["exp"], tz=UTC),
                iat=datetime.fromtimestamp(payload["iat"], tz=UTC),
                jti=jti,
                token_type=payload.get("type"),
            )
        except JWTError as e:
            logger.debug(f"Token validation details: {e}")
            logger.warning("Token validation failed")
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    def _is_token_revoked(self, jti: str) -> bool:
        """Check if a token is revoked (Redis or in-memory)."""
        if not jti:
            return True  # Reject tokens with null/empty JTI

        redis_client = get_redis()
        if redis_client:
            try:
                return bool(redis_client.exists(f"revoked_token:{jti}"))
            except (RedisError, ConnectionError, OSError):
                # Fall back to in-memory on Redis errors
                return jti in self._revoked_tokens
        return jti in self._revoked_tokens

    def revoke_token(self, jti: str):
        """Revoke a token by its ID."""
        # Immediate in-memory revocation (closes race window where _is_token_revoked
        # checks Redis before the Redis write completes)
        self._revoked_tokens.add(jti)

        # Persist to file as secondary backup
        self._persist_revocation_to_file(jti)

        # Persist to Redis for distributed deployments
        redis_client = get_redis()
        if redis_client:
            try:
                redis_client.setex(
                    f"revoked_token:{jti}",
                    7 * 24 * 60 * 60,  # 7 days (max token lifetime)
                    "1",
                )
            except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
                logger.warning(f"Redis revoke failed: {e}, in-memory revocation still active")

    def revoke_user(self, user_id: str):
        """Tombstone a deleted user so outstanding access tokens are rejected.

        A deleted user has no DB row, so get_current_user's is_active check no
        longer fires; this tombstone (checked on every request, distributed via
        Redis) rejects any of their still-unexpired tokens on all workers. TTL
        matches the maximum token lifetime.
        """
        if not user_id:
            return
        self._revoked_users.add(user_id)
        redis_client = get_redis()
        if redis_client:
            try:
                redis_client.setex(f"revoked_user:{user_id}", 7 * 24 * 60 * 60, "1")
            except (RedisError, ConnectionError, TimeoutError, OSError, RuntimeError) as e:
                logger.warning(f"Redis user-revoke failed: {e}, in-memory tombstone still active")

    def _is_user_revoked(self, user_id: str) -> bool:
        """Whether a user has been tombstoned (deleted)."""
        if not user_id:
            return False
        redis_client = get_redis()
        if redis_client:
            try:
                return bool(redis_client.exists(f"revoked_user:{user_id}"))
            except (RedisError, ConnectionError, OSError):
                return user_id in self._revoked_users
        return user_id in self._revoked_users

    # ==================== Azure AD Integration ====================

    async def _get_azure_jwks(self) -> dict:
        """Get Azure AD JWKS with 1-hour cache."""
        import time

        now = time.time()
        if (
            self._jwks_cache
            and self._jwks_cache_time
            and (now - self._jwks_cache_time) < self._jwks_cache_ttl
        ):
            return self._jwks_cache

        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=30.0)) as client:
            config_url = f"https://login.microsoftonline.com/{self.azure_tenant}/v2.0/.well-known/openid-configuration"
            config_resp = await client.get(config_url)
            config = config_resp.json()
            jwks_resp = await client.get(config["jwks_uri"])
            jwks = jwks_resp.json()

        self._jwks_cache = jwks
        self._jwks_cache_time = now
        return jwks

    async def verify_azure_token(self, token: str) -> dict:
        """Verify an Azure AD token."""
        jwks = await self._get_azure_jwks()

        # Decode and verify the token
        try:
            # Get the key ID from token header
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            # Find the matching public key
            public_key = None
            for key in jwks["keys"]:
                if key["kid"] == kid:
                    # PyJWT accepts both dict and JSON string for from_jwk
                    import json as json_module

                    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json_module.dumps(key))
                    break

            if not public_key:
                raise HTTPException(status_code=401, detail="Unable to find matching key")

            # Verify the token
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=self.azure_client_id,
                issuer=f"https://login.microsoftonline.com/{self.azure_tenant}/v2.0",
            )

            return payload

        except JWTError as e:
            logger.debug(f"Azure token validation details: {e}")
            logger.warning("Azure token validation failed")
            raise HTTPException(status_code=401, detail="Invalid or expired Azure token")

    async def verify_azure_identity(self, azure_token: str) -> dict:
        """Verify an Azure AD token and return the identity claims we act on.

        Returns ``{"id", "email", "name", "azure_oid", "tenant_id"}``. This
        deliberately carries NO roles: authorization is decided by the local
        account row (``users.roles``), never by the identity provider's
        token, so an admin's role changes take effect on the next login and
        a first-time SSO user gets the configured default rather than a
        privileged role.
        """
        payload = await self.verify_azure_token(azure_token)
        return {
            "id": payload.get("oid") or payload["sub"],
            "email": payload.get("email") or payload.get("preferred_username") or "",
            "name": payload.get("name") or "",
            "azure_oid": payload.get("oid"),
            "tenant_id": payload.get("tid"),
        }

    async def issue_azure_login(self, user: User, request: Request) -> dict:
        """Mint local tokens for an already-resolved SSO user and audit the login.

        ``user.roles`` must come from the database row, not from the token.
        """
        access_token = self.create_access_token(user)
        refresh_token = self.create_refresh_token(user)

        await audit_service.log_event(
            event_type=AuditEventType.LOGIN_SUCCESS,
            user_id=user.id,
            user_email=user.email,
            details={
                "method": "azure_ad",
                "tenant": user.tenant_id,
                "roles": [r.value for r in user.roles],
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",  # nosec B105 - OAuth2 token type, not a password
            "expires_in": self.access_token_expire.total_seconds(),
            "user": user.model_dump(),
        }

    # ==================== Authorization ====================

    def check_permission(self, user_roles: list[str], required_roles: list[UserRole]) -> bool:
        """Check if user has any of the required roles."""
        user_role_set = set(user_roles)
        required_role_set = {r.value for r in required_roles}
        return bool(user_role_set & required_role_set)

    def require_roles(self, *roles: UserRole):
        """Dependency to require specific roles."""

        async def check_roles(token_data: TokenData = Depends(get_current_user)):
            if not self.check_permission(token_data.roles, list(roles)):
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return token_data

        return check_roles


# ==================== FastAPI Dependencies ====================

security = HTTPBearer(auto_error=False)
auth_service = AuthService()


def _token_predates_password_change(token_iat: datetime, password_changed_at: datetime) -> bool:
    """True if a token issued at ``token_iat`` predates the last password change.

    ``password_changed_at`` is stored naive UTC (to match the Postgres TIMESTAMP
    WITHOUT TIME ZONE column); ``token_iat`` is tz-aware UTC. Both are normalized
    to naive UTC. A 5-second allowance absorbs clock skew between token issuance
    and the DB write so a token minted at reset time isn't spuriously rejected.
    """
    iat_naive = token_iat.astimezone(UTC).replace(tzinfo=None) if token_iat.tzinfo else token_iat
    pwc = (
        password_changed_at.replace(tzinfo=None)
        if password_changed_at.tzinfo
        else password_changed_at
    )
    return iat_naive < (pwc - timedelta(seconds=5))


async def get_current_user(
    request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenData | None:
    """Get the current authenticated user from the request."""
    if not credentials:
        # Fall back to httpOnly cookie
        cookie_token = request.cookies.get("access_token")
        if not cookie_token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        token = cookie_token
    else:
        token = credentials.credentials

    token_data = auth_service.verify_token(token)

    # Reject non-access tokens (e.g. refresh tokens used as access tokens)
    if token_data.token_type != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # Reject tokens belonging to a deleted (tombstoned) user. This runs before
    # the DB lookup so it catches users whose row is already gone — the exact
    # gap where the missing row would otherwise skip the is_active check.
    if auth_service._is_user_revoked(token_data.user_id):
        raise HTTPException(status_code=401, detail="Account disabled or deleted")

    # Verify user is still active in the database
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.db_models import User as DBUser

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DBUser.is_active, DBUser.password_changed_at).where(
                DBUser.id == token_data.user_id
            )
        )
        row = result.one_or_none()
        # If user not found in DB (e.g. demo user), skip the DB-backed checks.
        if row is not None:
            is_active, password_changed_at = row
            if not is_active:
                raise HTTPException(status_code=401, detail="Account disabled or deleted")
            # Invalidate any token issued before the last password change, so a
            # password reset immediately kills all outstanding access AND refresh
            # tokens without needing to track individual JTIs.
            if password_changed_at is not None and _token_predates_password_change(
                token_data.iat, password_changed_at
            ):
                raise HTTPException(status_code=401, detail="Session expired, please sign in again")

    # Enforce session validation.
    # IMPORTANT: resolve the client IP the same way create_session does
    # (get_client_ip honors X-Forwarded-For). Using request.client.host here
    # compares against the reverse-proxy IP (e.g. nginx / 127.0.0.1) while the
    # session was stored under the real client IP, so session IP binding fails
    # and every request 401s behind a proxy (Coolify/Traefik/nginx).
    from app.middleware.security import session_manager
    from app.utils.ip_resolution import get_client_ip

    session_valid = session_manager.validate_session(
        token_data.user_id,
        token_data.jti,
        ip_address=get_client_ip(request),
        token_exp=token_data.exp,
    )
    if not session_valid:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    return token_data


async def get_current_user_optional(
    request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenData | None:
    """Get the current user if authenticated, None otherwise.

    Delegates to ``get_current_user`` so a presented token receives the SAME
    checks as mandatory auth (token type, tombstone/revocation, active-user,
    password-change invalidation, session validation). A revoked or otherwise
    invalid token yields None — it must never authenticate.
    """
    token = credentials.credentials if credentials else request.cookies.get("access_token")
    if not token:
        return None

    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


def require_roles(*roles: UserRole):
    """Dependency that requires specific roles."""
    return Depends(auth_service.require_roles(*roles))


# ==================== Password Reset Support ====================


class PasswordResetService:
    """Handles password reset tokens and validation."""

    def __init__(self):
        self._reset_tokens = {}  # In-memory fallback

    @staticmethod
    def _hash_token(token: str) -> str:
        """Hash a reset token before using as a storage key.

        The raw token is only sent via email; storage only holds the hash.
        """
        import hashlib

        return hashlib.sha256(token.encode()).hexdigest()

    def generate_reset_token(self, email: str) -> str:
        """Generate a password reset token for an email."""
        import secrets
        from datetime import timedelta

        token = secrets.token_urlsafe(32)
        token_hash = self._hash_token(token)
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        data = {
            "email": email.lower(),
            "expires_at": expires_at.isoformat(),
        }

        redis_client = get_redis()
        if redis_client:
            try:
                import json

                redis_client.setex(
                    f"password_reset:{token_hash}",
                    3600,  # 1 hour TTL
                    json.dumps(data),
                )
                return token
            except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
                logger.warning(f"Redis store failed: {e}")

        # In-memory fallback
        self._reset_tokens[token_hash] = data
        return token

    def verify_reset_token(self, token: str) -> str | None:
        """Verify a reset token and return the email if valid."""
        import json

        token_hash = self._hash_token(token)

        redis_client = get_redis()
        if redis_client:
            try:
                data_str = redis_client.get(f"password_reset:{token_hash}")
                if data_str:
                    data = json.loads(data_str)
                    expires_at = datetime.fromisoformat(data["expires_at"])
                    if expires_at > datetime.now(UTC):
                        return data["email"]
                    # Token expired, delete it
                    redis_client.delete(f"password_reset:{token_hash}")
                return None
            except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
                logger.warning(f"Redis verify failed: {e}")

        # In-memory fallback
        data = self._reset_tokens.get(token_hash)
        if data:
            expires_at = datetime.fromisoformat(data["expires_at"])
            if expires_at > datetime.now(UTC):
                return data["email"]
            # Token expired, delete it
            del self._reset_tokens[token_hash]
        return None

    def invalidate_token(self, token: str):
        """Invalidate a used reset token."""
        token_hash = self._hash_token(token)

        redis_client = get_redis()
        if redis_client:
            try:
                redis_client.delete(f"password_reset:{token_hash}")
            except (RedisError, ConnectionError, OSError):
                pass

        if token_hash in self._reset_tokens:
            del self._reset_tokens[token_hash]


password_reset_service = PasswordResetService()
