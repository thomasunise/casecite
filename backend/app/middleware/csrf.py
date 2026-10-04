"""
CSRF Protection Middleware - Double-Submit Cookie Pattern

Provides Cross-Site Request Forgery protection using the double-submit cookie pattern:
1. Server sets a CSRF cookie on GET requests
2. Client includes the cookie value in X-CSRF-Token header on state-changing requests
3. Server validates that cookie and header match

Exempt paths:
- OAuth callbacks (already protected by state parameter)
- Public endpoints (health, config)
- Webhooks (authenticated via signatures)
"""

import hashlib
import hmac
import logging
import secrets

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger(__name__)

# Domain-separated CSRF signing key (HKDF from SECRET_KEY), independent of the
# JWT signing key and the data-encryption key. Cached after first derivation.
_CSRF_KEY_CACHE: bytes | None = None


def _csrf_key() -> bytes:
    global _CSRF_KEY_CACHE
    if _CSRF_KEY_CACHE is None:
        from app.utils.keys import derive_subkey

        _CSRF_KEY_CACHE = derive_subkey("csrf")
    return _CSRF_KEY_CACHE


def request_is_https(request: Request) -> bool:
    """Determine whether the original client request used HTTPS.

    Honors the reverse proxy's X-Forwarded-Proto header (set by
    Coolify/Traefik/nginx) so the CSRF cookie's Secure flag is correct
    whether the app is reached directly over HTTP (e.g. a bare IP demo)
    or behind a TLS-terminating proxy.
    """
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        # May be a comma-separated list; the first value is the client-facing scheme.
        return forwarded_proto.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


def cookie_secure(request: Request) -> bool:
    """Secure flag for the cookies this app sets.

    Production (DEBUG=false) always sets Secure: the forwarded-proto header is
    not a reliable signal (a proxy hop that overwrites X-Forwarded-Proto with
    its own plain-HTTP scheme would otherwise strip the flag from auth cookies
    behind a TLS-terminating edge), and production must be served over TLS
    anyway. Local development falls back to the observed scheme so cookies
    still work over plain http://localhost.
    """
    return (not settings.debug) or request_is_https(request)


def generate_signed_csrf_token() -> str:
    """Generate and sign a new CSRF token (for use outside middleware)."""
    token = secrets.token_urlsafe(32)
    signature = hmac.new(_csrf_key(), token.encode(), hashlib.sha256).hexdigest()
    return f"{token}.{signature}"


def verify_csrf_token(signed_token: str) -> bool:
    """Verify a signed CSRF token (for use outside middleware)."""
    if not signed_token or "." not in signed_token:
        return False
    try:
        token, signature = signed_token.rsplit(".", 1)
        expected_signature = hmac.new(_csrf_key(), token.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected_signature)
    except (ValueError, TypeError):
        return False


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection using double-submit cookie pattern.

    How it works:
    1. On GET requests, set a CSRF cookie with a random token
    2. On POST/PUT/DELETE requests, validate that:
       - X-CSRF-Token header is present
       - Header value matches the cookie value
    """

    def __init__(self, app, cookie_name: str = "_csrf", header_name: str = "X-CSRF-Token"):
        super().__init__(app)
        self.cookie_name = cookie_name
        self.header_name = header_name

        # Paths exempt from CSRF protection
        self.exempt_paths: set[str] = {
            "/health",
            "/ready",
            "/metrics",
            # Auth endpoints (protected by their own mechanisms: tokens, rate limiting)
            # Note: /auth/refresh is intentionally NOT exempt — it relies on
            # httpOnly cookies so it must be CSRF-protected.
            "/api/v1/auth/demo/login",
            "/api/v1/auth/azure/login",
            "/api/v1/auth/forgot-password",
            "/api/v1/auth/login",
            "/api/v1/auth/reset-password",
            "/api/v1/auth/verify-reset-token",
            # MFA second-step verification (pre-auth, like login)
            "/api/v1/auth/mfa/verify",
            # OAuth callbacks are protected by state parameter
            "/api/v1/connectors/google/callback",
            "/api/v1/connectors/microsoft/callback",
            "/api/v1/connectors/dropbox/callback",
            "/api/v1/connectors/box/callback",
            # CSRF token endpoint (handles its own cookie setting)
            "/api/v1/csrf-token",
        }

        # Paths with prefix exemption
        self.exempt_prefixes: set[str] = {
            "/docs",
            "/redoc",
            "/openapi.json",
        }

        # Methods that don't need CSRF protection
        self.safe_methods = {"GET", "HEAD", "OPTIONS", "TRACE"}

    def _is_exempt(self, path: str) -> bool:
        """Check if path is exempt from CSRF protection."""
        if path in self.exempt_paths:
            return True
        for prefix in self.exempt_prefixes:
            if path.startswith(prefix):
                return True
        return False

    def _generate_token(self) -> str:
        """Generate a cryptographically secure CSRF token."""
        return secrets.token_urlsafe(32)

    def _sign_token(self, token: str) -> str:
        """Sign a token with the secret key for additional validation."""
        signature = hmac.new(_csrf_key(), token.encode(), hashlib.sha256).hexdigest()
        return f"{token}.{signature}"

    def _verify_token(self, signed_token: str) -> bool:
        """Verify a signed token."""
        if not signed_token or "." not in signed_token:
            return False
        try:
            token, signature = signed_token.rsplit(".", 1)
            expected_signature = hmac.new(_csrf_key(), token.encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(signature, expected_signature)
        except (ValueError, TypeError):
            return False

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with CSRF validation."""
        path = request.url.path
        method = request.method.upper()

        # Skip CSRF for exempt paths
        if self._is_exempt(path):
            return await call_next(request)

        # Skip CSRF only when BOTH debug mode AND explicit CSRF_DISABLED are set.
        # This prevents CSRF from being silently disabled if DEBUG is accidentally
        # left enabled in a production-like environment.
        if settings.debug and getattr(settings, "csrf_disabled", False):
            return await call_next(request)

        # Safe methods: set CSRF cookie if not present
        if method in self.safe_methods:
            response = await call_next(request)

            # Set CSRF cookie if not already present
            existing_cookie = request.cookies.get(self.cookie_name)
            if not existing_cookie or not self._verify_token(existing_cookie):
                csrf_token = self._sign_token(self._generate_token())
                response.set_cookie(
                    key=self.cookie_name,
                    value=csrf_token,
                    httponly=False,  # Must be readable by JavaScript
                    secure=cookie_secure(request),  # always Secure in production
                    samesite="lax",  # "lax" allows OAuth callback flows; "strict" would block them
                    max_age=3600,  # 1 hour
                    path="/",
                )

            return response

        # State-changing methods: validate CSRF token
        cookie_token = request.cookies.get(self.cookie_name)
        header_token = request.headers.get(self.header_name)

        # Both must be present
        if not cookie_token or not header_token:
            logger.warning(f"CSRF validation failed: missing token for {method} {path}")
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing. Please refresh the page and try again."},
            )

        # Tokens must match (constant-time comparison)
        if not hmac.compare_digest(cookie_token, header_token):
            logger.warning(f"CSRF validation failed: token mismatch for {method} {path}")
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token invalid. Please refresh the page and try again."},
            )

        # Verify token signature
        if not self._verify_token(cookie_token):
            logger.warning(f"CSRF validation failed: invalid signature for {method} {path}")
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token invalid. Please refresh the page and try again."},
            )

        # CSRF validation passed
        return await call_next(request)


# Optional: CSRF token endpoint for SPA frontends
def get_csrf_router():
    """Create a router with CSRF token endpoint for SPA frontends."""
    from fastapi import APIRouter

    router = APIRouter(tags=["csrf"])

    @router.get("/csrf-token")
    async def get_csrf_token(request: Request):
        """
        Get a CSRF token for use in subsequent requests.

        Frontend should:
        1. Call this endpoint on page load
        2. Include the token in X-CSRF-Token header on POST/PUT/DELETE requests
        """
        existing = request.cookies.get("_csrf")

        if existing and verify_csrf_token(existing):
            return {
                "csrf_token": existing,
                "header_name": "X-CSRF-Token",
                "note": "Include this token in X-CSRF-Token header on state-changing requests",
            }

        # First visit or expired token - generate new token and set cookie
        token = generate_signed_csrf_token()
        from fastapi.responses import JSONResponse

        response = JSONResponse(
            content={
                "csrf_token": token,
                "header_name": "X-CSRF-Token",
                "note": "Include this token in X-CSRF-Token header on state-changing requests",
            }
        )
        response.set_cookie(
            key="_csrf",
            value=token,
            httponly=False,  # Must be readable by JavaScript
            secure=cookie_secure(request),  # always Secure in production
            samesite="lax",
            max_age=3600,
            path="/",
        )
        return response

    return router
