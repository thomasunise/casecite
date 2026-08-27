"""
Security Middleware

Provides:
- Per-IP rate limiting and per-account login lockout
- Security headers (CSP, HSTS, frame/nosniff, permissions policy)
- Request logging
- Session tracking keyed by token JTI
"""

import json
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.redis_utils import RedisError, _is_production, get_redis, require_redis
from app.services.audit import AuditEventType, audit_service

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter.

    Uses Redis when available for distributed deployments.
    Falls back to in-memory for single-instance deployments.
    """

    def __init__(self):
        # In-memory fallback: {ip: {endpoint: [timestamps]}}
        self._requests: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # Cleanup stale entries every 5 minutes

        # Rate limits: (requests, window_seconds)
        # Stricter limits for security-sensitive endpoints
        self.limits = {
            "default": (100, 60),  # 100 req/min
            "/api/v1/chat": (20, 60),  # 20 req/min (expensive)
            "/api/v1/documents": (50, 60),  # 50 req/min
            "/api/v1/auth/login": (
                3,
                300,
            ),  # 3 per 5 min (stricter brute force prevention)
            "/api/v1/auth/demo/login": (3, 300),  # 3 per 5 min
            "/api/v1/auth/register": (3, 300),  # 3 per 5 min (PBKDF2 CPU + enumeration)
            "/api/v1/auth/change-password": (5, 300),  # 5 per 5 min
            "/api/v1/auth/refresh": (10, 60),  # 10 per min (token minting)
            "/api/v1/auth/forgot-password": (3, 300),  # 3 per 5 min
            "/api/v1/auth/mfa/verify": (5, 300),  # 5 per 5 min (brute-force protection)
            "/api/v1/auth/mfa/recovery": (5, 300),  # 5 per 5 min (brute-force protection)
            "/api/v1/auth/mfa/recovery-codes": (5, 300),  # 5 per 5 min (code-proof gated)
            # Expensive AI operations — stricter limits to prevent cost abuse
            "/api/v1/discovery/suggest-objections": (10, 60),  # 10 per min
            "/api/v1/discovery/detect-privilege": (10, 60),  # 10 per min
            "/api/v1/discovery/esi-protocol": (5, 60),  # 5 per min
            "/api/v1/legal-docs/draft": (5, 60),  # 5 per min
            "/api/v1/legal-docs/compare": (10, 60),  # 10 per min
            "/api/v1/pleadings/validate-rules": (10, 60),  # 10 per min
            "/api/v1/pleadings/generate-toc": (10, 60),  # 10 per min
            "/api/v1/legal-research/cases/compare": (10, 60),  # 10 per min
            "/api/v1/strategy/brief": (5, 60),  # 5 per min
            # Job polling
            "/api/v1/jobs": (30, 60),  # 30 per min (polling)
            # Key management — prevent brute-force key enumeration
            "/api/v1/user/keys/save": (5, 60),  # 5 per min
            "/api/v1/user/keys/delete": (10, 60),  # 10 per min
            "/api/v1/auth/reset-password": (5, 300),  # 5 per 5 min
        }

        # Track failures for progressive delays
        self._failure_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        # Account-level lockout tracking: {email: [timestamps]}
        self._account_failures: dict[str, list[float]] = defaultdict(list)
        self._account_lockout_threshold = 5  # failures before lockout
        self._account_lockout_window = 900  # 15 minutes
        self._account_lockout_duration = 900  # 15 minutes

    def _get_limit(self, path: str) -> tuple:
        """Get rate limit for a path (exact match or path prefix with /)."""
        for pattern, limit in self.limits.items():
            if pattern == "default":
                continue
            # Exact match or proper path prefix (prevents /auth/login matching /auth/login-history)
            if path == pattern or path.startswith(pattern + "/"):
                return limit
        return self.limits["default"]

    def _cleanup_stale_entries(self):
        """Periodically remove stale IPs/paths from in-memory storage to prevent unbounded growth."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now

        # Find the maximum window across all limits
        max_window = max(w for _, w in self.limits.values())
        cutoff = now - max_window

        stale_ips = []
        for ip, paths in self._requests.items():
            stale_paths = []
            for path, timestamps in paths.items():
                # Remove timestamps older than the max window
                fresh = [t for t in timestamps if t > cutoff]
                if fresh:
                    paths[path] = fresh
                else:
                    stale_paths.append(path)
            for p in stale_paths:
                del paths[p]
            if not paths:
                stale_ips.append(ip)
        for ip in stale_ips:
            del self._requests[ip]

    def is_allowed(self, ip: str, path: str) -> tuple[bool, dict]:
        """Check if request is allowed under rate limit."""
        self._cleanup_stale_entries()
        max_requests, window = self._get_limit(path)

        # Use Redis if available (sliding window with sorted sets)
        redis_client = require_redis()
        if redis_client:
            try:
                now = time.time()
                key = f"rate_limit:{ip}:{path}"

                # Remove old entries and count current
                pipe = redis_client.pipeline()
                pipe.zremrangebyscore(key, 0, now - window)
                pipe.zcard(key)
                pipe.zadd(key, {str(now): now})
                pipe.expire(key, window)
                results = pipe.execute()

                current_count = results[1]

                if current_count >= max_requests:
                    return False, {
                        "limit": max_requests,
                        "remaining": 0,
                        "retry_after": window,
                    }

                return True, {
                    "limit": max_requests,
                    "remaining": max_requests - current_count - 1,
                    "reset": int(now + window),
                }
            except (RedisError, ConnectionError, OSError):  # nosec B110 - Intentional fallback to in-memory
                # In production, fail closed — don't fall through to in-memory
                if _is_production():
                    logger.critical("Redis error during rate limiting in production")
                    return False, {
                        "limit": max_requests,
                        "remaining": 0,
                        "retry_after": 30,
                        "unavailable": True,
                    }
        elif _is_production():
            # Redis required in production — fail closed
            return False, {
                "limit": max_requests,
                "remaining": 0,
                "retry_after": 30,
                "unavailable": True,
            }

        # In-memory fallback (dev/demo only)
        now = time.time()
        cutoff = now - window

        # Clean old requests
        self._requests[ip][path] = [t for t in self._requests[ip][path] if t > cutoff]

        current_count = len(self._requests[ip][path])

        if current_count >= max_requests:
            retry_after = int(window - (now - self._requests[ip][path][0]))
            return False, {
                "limit": max_requests,
                "remaining": 0,
                "retry_after": retry_after,
            }

        # Record this request
        self._requests[ip][path].append(now)

        return True, {
            "limit": max_requests,
            "remaining": max_requests - current_count - 1,
            "retry_after": 0,
        }

    def record_login_failure(self, email: str):
        """Record a failed login attempt for account-level lockout."""
        if not email:
            return
        email = email.lower().strip()
        now = time.time()

        redis_client = require_redis()
        if redis_client:
            try:
                key = f"account_lockout:{email}"
                redis_client.zadd(key, {str(now): now})
                redis_client.zremrangebyscore(key, 0, now - self._account_lockout_window)
                redis_client.expire(
                    key, self._account_lockout_window + self._account_lockout_duration
                )
                return
            except (RedisError, ConnectionError, OSError):
                if _is_production():
                    logger.critical(
                        "Redis error recording login failure in production — "
                        "falling through to in-memory (is_account_locked fails closed)"
                    )

        # In-memory fallback
        cutoff = now - self._account_lockout_window
        self._account_failures[email] = [t for t in self._account_failures[email] if t > cutoff]
        self._account_failures[email].append(now)

    def _get_lockout_duration(self, failure_count: int) -> int:
        """Exponential backoff lockout: 15min, 30min, 1hr, 2hr, max 4hr."""
        if failure_count < self._account_lockout_threshold:
            return 0
        # How many times the threshold has been exceeded
        multiplier = min(2 ** (failure_count // self._account_lockout_threshold - 1), 16)
        return self._account_lockout_duration * multiplier

    def is_account_locked(self, email: str) -> bool:
        """Check if an account is locked due to too many failed attempts."""
        if not email:
            return False
        email = email.lower().strip()
        now = time.time()

        redis_client = require_redis()
        if redis_client:
            try:
                key = f"account_lockout:{email}"
                cutoff = now - self._account_lockout_window
                redis_client.zremrangebyscore(key, 0, cutoff)
                count = redis_client.zcard(key)
                if count < self._account_lockout_threshold:
                    return False
                # Exponential backoff: check if lockout duration has elapsed
                last_failure = redis_client.zrange(key, -1, -1, withscores=True)
                if last_failure:
                    last_ts = last_failure[0][1]
                    lockout_secs = self._get_lockout_duration(count)
                    return (now - last_ts) < lockout_secs
                return True
            except (RedisError, ConnectionError, OSError):
                if _is_production():
                    logger.critical(
                        "Redis error checking account lockout in production — "
                        "failing closed (treating as locked)"
                    )
                    return True
        elif _is_production():
            # Redis required in production — fail closed (treat as locked)
            return True

        # In-memory fallback (dev/demo only)
        cutoff = now - self._account_lockout_window
        self._account_failures[email] = [t for t in self._account_failures[email] if t > cutoff]
        count = len(self._account_failures[email])
        if count < self._account_lockout_threshold:
            return False
        # Exponential backoff
        last_ts = self._account_failures[email][-1]
        lockout_secs = self._get_lockout_duration(count)
        return (now - last_ts) < lockout_secs

    def clear_account_lockout(self, email: str):
        """Clear lockout state after successful login."""
        if not email:
            return
        email = email.lower().strip()

        redis_client = get_redis()
        if redis_client:
            try:
                redis_client.delete(f"account_lockout:{email}")
            except (RedisError, ConnectionError, OSError):
                pass

        self._account_failures.pop(email, None)


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive security middleware.
    """

    def __init__(self, app):
        super().__init__(app)
        self.rate_limiter = RateLimiter()

        # Allowed origins for CORS
        self.allowed_origins = {"*"}  # Configure in production

        # Paths that don't require auth
        self.public_paths = {
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/api/v1/auth/login",
            "/api/v1/auth/demo/login",
            "/api/v1/auth/azure/callback",
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()

        # Get client IP (handle proxies)
        client_ip = self._get_client_ip(request)

        # Rate limiting
        allowed, rate_info = self.rate_limiter.is_allowed(client_ip, request.url.path)
        if not allowed:
            # Redis unavailable in production — return 503, not 429
            if rate_info.get("unavailable"):
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Service temporarily unavailable"},
                    headers={"Retry-After": "30"},
                )

            await audit_service.log_event(
                event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
                ip_address=client_ip,
                details={"path": request.url.path, "limit": rate_info["limit"]},
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
                headers={
                    "Retry-After": str(rate_info["retry_after"]),
                    "X-RateLimit-Limit": str(rate_info["limit"]),
                    "X-RateLimit-Remaining": "0",
                },
            )

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:  # Intentional broad catch - error boundary
            # Log unexpected errors
            await audit_service.log_event(
                event_type=AuditEventType.SUSPICIOUS_ACTIVITY,
                ip_address=client_ip,
                details={"error": str(e), "path": request.url.path},
                success=False,
            )
            raise

        # Add security headers
        response = self._add_security_headers(response, rate_info, request.url.path)

        # Log request
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Get real client IP, handling proxies.

        Delegates to the shared ip_resolution utility which supports
        CIDR-based trusted proxy matching and secure right-to-left
        X-Forwarded-For walking with IP validation.
        """
        from app.utils.ip_resolution import get_client_ip

        return get_client_ip(request)

    def _add_security_headers(
        self, response: Response, rate_info: dict, request_path: str = ""
    ) -> Response:
        """Add security headers to response."""
        # Rate limit headers
        response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(rate_info["remaining"])

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # Content Security Policy
        # Note: 'unsafe-inline' for styles is often needed for frameworks like React
        # 'unsafe-eval' should be avoided - if needed, use nonce-based CSP
        # Script sources are the ones the app actually loads: Google Sign-In
        # (accounts.google.com), the Google Picker loader (apis.google.com), and
        # the Dropbox Chooser (www.dropbox.com). No CDN (unpkg/jsdelivr) is used.
        # frame-src allows the Google Picker iframe.
        # Source lists cover the scripts/frames the app actually loads: Google
        # Sign-In + Picker (accounts/apis.google.com), Dropbox Chooser
        # (www.dropbox.com), and the Box Content Picker (script+CSS from
        # cdn01.boxcdn.net, API calls to api.box.com). frame-src includes blob:
        # for the in-app PDF viewer's blob: iframe.
        if settings.debug:
            # Local development: permissive (unsafe-inline) for the Vite dev server
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://accounts.google.com https://apis.google.com https://www.dropbox.com https://cdn01.boxcdn.net; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com https://cdn01.boxcdn.net; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self' https://api.openai.com https://api.anthropic.com https://login.microsoftonline.com https://accounts.google.com https://apis.google.com https://www.googleapis.com https://api.box.com https://upload.box.com; "
                "frame-src 'self' blob: https://accounts.google.com https://docs.google.com; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
        else:
            # Production mode: strict CSP — no unsafe-inline for scripts
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' https://accounts.google.com https://apis.google.com https://www.dropbox.com https://cdn01.boxcdn.net; "
                "style-src 'self' https://fonts.googleapis.com https://accounts.google.com https://cdn01.boxcdn.net; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self' https://api.openai.com https://api.anthropic.com https://login.microsoftonline.com https://accounts.google.com https://apis.google.com https://www.googleapis.com https://api.box.com https://upload.box.com; "
                "frame-src 'self' blob: https://accounts.google.com https://docs.google.com; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )

        # HSTS (production only — never in local development)
        # Enables strict HTTPS for 1 year, including subdomains
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Cache-Control for API responses (prevent caching of sensitive data)
        # Only apply to API endpoints, not static files
        if "/api/" in request_path:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        return response


class SessionManager:
    """
    Secure session management.

    - Session timeouts
    - Concurrent session limits
    - Session binding (IP, user agent)
    - File-based persistence to survive restarts without Redis
    """

    def __init__(self):
        # {user_id: [session_info]}
        self._sessions: dict[str, list] = defaultdict(list)
        self.max_sessions_per_user = 5
        self.session_timeout = timedelta(hours=8)
        self._last_cleanup = datetime.now(UTC)
        self._cleanup_interval = timedelta(minutes=15)

        # File-based session persistence
        # Lives beside the other data-dir stores (upload_dir's parent IS the data
        # dir; the previous extra "data" segment created data/data/).
        self._session_file = Path(settings.upload_dir).parent / "sessions.jsonl"
        self._load_sessions_from_file()

    # ---------- File-based persistence ----------

    def _load_sessions_from_file(self):
        """Restore unexpired sessions from file on startup."""
        try:
            if not self._session_file.exists():
                return
            now = datetime.now(UTC)
            loaded = 0
            with open(self._session_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        expires_at = datetime.fromisoformat(entry["expires_at"])
                        if expires_at <= now:
                            continue
                        self._sessions[entry["user_id"]].append(
                            {
                                "jti": entry["jti"],
                                "ip_address": entry.get("ip_address", "unknown"),
                                "user_agent": entry.get("user_agent", ""),
                                "created_at": datetime.fromisoformat(entry["created_at"]),
                                "expires_at": expires_at,
                                "last_activity": datetime.fromisoformat(
                                    entry.get("last_activity", entry["created_at"])
                                ),
                            }
                        )
                        loaded += 1
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
            if loaded:
                logger.info(f"Restored {loaded} sessions from file")
        except OSError as e:
            logger.warning(f"Could not load sessions from file: {e}")

    def _persist_session(self, user_id: str, session: dict):
        """Append a session to the persistence file."""
        try:
            self._session_file.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "user_id": user_id,
                "jti": session["jti"],
                "ip_address": session["ip_address"],
                "user_agent": session["user_agent"],
                "created_at": session["created_at"].isoformat(),
                "expires_at": session["expires_at"].isoformat(),
                "last_activity": session["last_activity"].isoformat(),
            }
            with open(self._session_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
            # Restrict file permissions to owner only (0o600)
            try:
                import os
                import stat

                os.chmod(self._session_file, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass  # Windows may not support chmod
        except OSError:
            pass  # Best-effort persistence

    def _rewrite_session_file(self):
        """Rewrite the session file with only active sessions (compaction)."""
        try:
            self._session_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._session_file, "w") as f:
                for user_id, sessions in self._sessions.items():
                    for s in sessions:
                        entry = {
                            "user_id": user_id,
                            "jti": s["jti"],
                            "ip_address": s["ip_address"],
                            "user_agent": s["user_agent"],
                            "created_at": s["created_at"].isoformat(),
                            "expires_at": s["expires_at"].isoformat(),
                            "last_activity": s["last_activity"].isoformat(),
                        }
                        f.write(json.dumps(entry) + "\n")
            # Restrict file permissions to owner only (0o600)
            try:
                import os
                import stat

                os.chmod(self._session_file, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass  # Windows may not support chmod
        except OSError:
            pass

    def _cleanup_expired_sessions(self):
        """Periodically remove all expired sessions to prevent unbounded memory growth."""
        now = datetime.now(UTC)
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now

        stale_users = []
        for user_id, sessions in self._sessions.items():
            self._sessions[user_id] = [s for s in sessions if s["expires_at"] > now]
            if not self._sessions[user_id]:
                stale_users.append(user_id)
        for uid in stale_users:
            del self._sessions[uid]

        # Compact the session persistence file
        self._rewrite_session_file()

    def create_session(self, user_id: str, ip_address: str, user_agent: str, jti: str) -> bool:
        """Create a new session, enforcing limits."""
        self._cleanup_expired_sessions()
        now = datetime.now(UTC)

        # Clean expired sessions
        self._sessions[user_id] = [s for s in self._sessions[user_id] if s["expires_at"] > now]

        # Check session limit
        if len(self._sessions[user_id]) >= self.max_sessions_per_user:
            # Remove oldest session
            self._sessions[user_id].sort(key=lambda s: s["created_at"])
            self._sessions[user_id].pop(0)

        # Add new session
        session = {
            "jti": jti,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "created_at": now,
            "expires_at": now + self.session_timeout,
            "last_activity": now,
        }
        self._sessions[user_id].append(session)
        self._persist_session(user_id, session)

        return True

    def validate_session(
        self, user_id: str, jti: str, ip_address: str = None, token_exp: datetime = None
    ) -> bool:
        """Validate a session is still valid."""
        now = datetime.now(UTC)

        # Enforce JWT expiration independently of session expiration
        if token_exp is not None and token_exp < now:
            return False

        for session in self._sessions.get(user_id, []):
            if session["jti"] == jti:
                # Check expiration
                if session["expires_at"] < now:
                    return False

                # Check IP binding if enabled
                if settings.enforce_session_ip_binding and ip_address:
                    if session["ip_address"] != ip_address:
                        return False

                # Update last activity
                session["last_activity"] = now
                return True

        return False

    def terminate_session(self, user_id: str, jti: str):
        """Terminate a specific session."""
        self._sessions[user_id] = [s for s in self._sessions[user_id] if s["jti"] != jti]
        # Compact the persistence file immediately: a terminated session must
        # not survive on disk until the periodic 15-minute compaction.
        self._rewrite_session_file()

    def terminate_all_sessions(self, user_id: str):
        """Terminate all sessions for a user."""
        self._sessions[user_id] = []
        # Compact the persistence file immediately (see terminate_session).
        self._rewrite_session_file()

    def get_active_sessions(self, user_id: str) -> list:
        """Get all active sessions for a user (sanitized for API response)."""
        now = datetime.now(UTC)
        return [
            {
                "created_at": s["created_at"].isoformat(),
                "last_activity": s["last_activity"].isoformat(),
                "ip_address": s["ip_address"][:20] + "..."
                if len(s["ip_address"]) > 20
                else s["ip_address"],
            }
            for s in self._sessions.get(user_id, [])
            if s["expires_at"] > now
        ]

    def get_active_sessions_raw(self, user_id: str) -> list:
        """Get all active sessions with JTIs (internal use for token revocation)."""
        now = datetime.now(UTC)
        return [s for s in self._sessions.get(user_id, []) if s["expires_at"] > now]


# Global instances
session_manager = SessionManager()
account_lockout = RateLimiter()  # Shared instance for account-level lockout
