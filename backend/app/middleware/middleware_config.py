"""
Middleware Configuration

Configures all middleware for the FastAPI application:
CORS, HTTPS redirect, TrustedHost, SecurityMiddleware, CSRFMiddleware.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.middleware.csrf import CSRFMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.security import SecurityMiddleware

logger = logging.getLogger(__name__)

# Hosts the in-container healthcheck uses to reach the app.
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1")


def configure_middleware(app: FastAPI) -> None:
    """Register all middleware on the FastAPI application."""

    # --- Configuration ---

    # HTTPS redirect - Enable for production deployments without a reverse proxy
    # Most deployments use a reverse proxy (Caddy, nginx, AWS ALB) that handles HTTPS
    # Set FORCE_HTTPS=true environment variable to enable redirect at the app level
    force_https = os.environ.get("FORCE_HTTPS", "").lower() == "true"

    # Trusted hosts (configure for your domain)
    # In production, set ALLOWED_HOSTS environment variable
    allowed_hosts_env = os.environ.get("ALLOWED_HOSTS", "")
    configured_hosts = [h.strip() for h in allowed_hosts_env.split(",") if h.strip()]
    if configured_hosts:
        # Loopback is always allowed alongside the configured hostnames: the
        # container healthcheck (and the bundled nginx/Caddy probes) reach the
        # app as http://localhost:8000, so a public-hostname-only list would
        # 400 every probe and the container would never turn healthy. A
        # loopback Host header is only reachable from inside the container or
        # its private network, never through the public proxy.
        allowed_hosts = list(dict.fromkeys([*configured_hosts, *_LOOPBACK_HOSTS]))
    elif settings.debug:
        allowed_hosts = ["*"]
    else:
        allowed_hosts = list(_LOOPBACK_HOSTS)
        logger.warning(
            "ALLOWED_HOSTS is not set in production — TrustedHost will reject every "
            "request whose Host header isn't localhost (all real traffic 400s). Set "
            "ALLOWED_HOSTS to this instance's public hostname(s)."
        )

    # A deliberate localhost-only instance (the documented DOMAIN=localhost
    # trial): every configured host is loopback, so nothing public can reach it.
    localhost_trial = bool(configured_hosts) and all(
        h.split(":")[0].lower() in _LOOPBACK_HOSTS for h in configured_hosts
    )

    # Behind a reverse proxy the trusted-proxy list must name the proxy, or every
    # client collapses to the proxy IP (breaking per-IP rate limits, account
    # lockout, and audit attribution). The 127.0.0.1 default is the footgun.
    if not settings.debug:
        tp_env = os.environ.get("TRUSTED_PROXIES", "").strip()
        if tp_env in ("", "127.0.0.1", "127.0.0.1/32", "localhost"):
            logger.warning(
                "TRUSTED_PROXIES is unset or localhost-only in production. If this "
                "instance runs behind a reverse proxy (Coolify/Traefik/nginx), set "
                "TRUSTED_PROXIES to the proxy's IP/subnet — otherwise all clients "
                "resolve to the proxy IP and one user's failed logins can lock out "
                "everyone."
            )

    # CORS - configure for your frontend URL
    # In production, set CORS_ORIGINS environment variable
    # SECURITY: Never use credentials=True with origins=["*"]
    cors_origins_env = os.environ.get("CORS_ORIGINS", "")

    if cors_origins_env:
        cors_origins = [o.strip() for o in cors_origins_env.split(",")]
        cors_allow_credentials = True  # Safe with explicit origins
        # Validate CORS origins in production (block localhost, warn on HTTP)
        if not settings.debug:
            for origin in cors_origins:
                if any(
                    local in origin.lower()
                    for local in ["localhost", "127.0.0.1", "0.0.0.0"]  # nosec B104 - denylist for validation, not a bind address
                ):
                    if localhost_trial:
                        # ALLOWED_HOSTS is loopback-only, so this instance is not
                        # publicly reachable and a localhost origin is the only
                        # one that can work.
                        logger.warning(
                            f"CORS origin '{origin}' is a localhost origin. Accepted because "
                            "ALLOWED_HOSTS is localhost-only (local trial); set DOMAIN / "
                            "ALLOWED_HOSTS / CORS_ORIGINS to a real hostname before exposing "
                            "this instance."
                        )
                        continue
                    raise ValueError(
                        f"SECURITY ERROR: Localhost origins not allowed in production: {origin}. "
                        "Remove localhost origins from CORS_ORIGINS for production deployments."
                    )
                if origin.startswith("http://") and not origin.startswith("https://"):
                    logger.warning(
                        f"SECURITY WARNING: CORS origin '{origin}' uses HTTP instead of HTTPS. "
                        "HTTPS is strongly recommended for production."
                    )
    elif settings.debug:
        # Local development — explicit origins so credentials: 'include' works
        cors_origins = [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
        ]
        cors_allow_credentials = True  # Required for httpOnly cookie auth
        logger.warning("CORS: Using localhost origins with credentials (development mode)")
    else:
        # Production without CORS_ORIGINS - refuse to start
        raise ValueError(
            "CONFIGURATION ERROR: CORS_ORIGINS must be set for production. "
            "Set CORS_ORIGINS environment variable with your frontend domains "
            "(e.g., CORS_ORIGINS=https://app.yourdomain.com,https://yourdomain.com). "
            "Localhost origins are not allowed in production."
        )

    # PostgreSQL TLS is enforced in app/database.py via DB_SSL (require / internal);
    # asyncpg does not accept an `sslmode` URL parameter, so nothing is checked here.

    # Allowed CORS headers
    cors_headers = (
        ["*"]
        if settings.debug
        else [
            "Content-Type",
            "Authorization",
            "X-Request-ID",
            "X-CSRF-Token",
        ]
    )

    # --- Register Middleware ---
    # In Starlette, last registered = outermost (processes request first, response last).
    # Desired processing order: CORS -> HTTPS -> TrustedHost -> RequestId -> Security -> CSRF -> App
    # This ensures CORS headers are on ALL responses (including 429 rate limit, 403 blocked).

    # CSRF protection (innermost - closest to app)
    # Always registered: the middleware itself skips validation only when BOTH
    # settings.debug AND settings.csrf_disabled are true (see csrf.py), so a
    # stray DEBUG=true can no longer silently remove CSRF protection.
    app.add_middleware(CSRFMiddleware)
    logger.info("CSRF protection middleware enabled")

    # Request ID (generates or propagates X-Request-ID for tracing)
    app.add_middleware(RequestIdMiddleware)

    # Security middleware (rate limiting, security headers, IP blocking)
    app.add_middleware(SecurityMiddleware)

    # Trusted hosts
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    # HTTPS redirect (conditional)
    if force_https and not settings.debug:
        app.add_middleware(HTTPSRedirectMiddleware)
        logger.info("HTTPS redirect middleware enabled")

    # CORS (outermost - ensures ALL responses include CORS headers, including 429/403 errors)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=cors_headers,
        expose_headers=[
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-Process-Time",
            "X-Etag-Id",
            "ETag",
            "X-Request-ID",
        ],
    )
