"""
System Router - Health and Metrics Endpoints

Provides:
- Root endpoint (API info / frontend redirect)
- Health check
- Readiness check (Kubernetes)
- Prometheus-compatible metrics
"""

import asyncio
import logging
import os
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from jwt.exceptions import PyJWTError as JWTError
from sqlalchemy.exc import DBAPIError, OperationalError

from app.config import settings
from app.models.responses.system import (
    HealthResponse,
    MetricsResponse,
    ReadyResponse,
)
from app.redis_utils import RedisError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["System"])

# Build/process fingerprint. version = git sha baked into the image at build
# (Coolify passes SOURCE_COMMIT); started_at = when THIS process booted.
# Together they make "which build/container answered me?" checkable from a
# browser: refresh /health — a changing started_at means multiple containers
# are serving one URL, which the embedded vector store cannot support.
APP_VERSION = os.environ.get("SOURCE_COMMIT", os.environ.get("GIT_SHA", "unknown"))[:12]
PROCESS_STARTED_AT = datetime.now(UTC).isoformat()

# Bound for blocking probes moved off the event loop via asyncio.to_thread.
_PROBE_TIMEOUT_SECONDS = 5.0


def _redis_ping() -> None:
    """Blocking Redis connectivity probe (call via asyncio.to_thread)."""
    import redis

    r = redis.from_url(settings.redis_url, socket_timeout=2)
    r.ping()


def _redis_memory_info() -> dict:
    """Blocking Redis INFO memory probe (call via asyncio.to_thread)."""
    import redis

    r = redis.from_url(settings.redis_url, socket_timeout=2)
    return r.info("memory")


@router.get("/", response_model=None)
async def root() -> dict | FileResponse:
    """Root endpoint - serves frontend if built, otherwise returns API info."""
    _index = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "frontend",
        "dist",
        "index.html",
    )
    if os.path.exists(_index):
        return FileResponse(_index)
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs" if settings.debug else "disabled",
    }


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> dict:
    """
    Health check endpoint.

    Used by load balancers and monitoring.

    In production mode the public response is minimal (status + timestamp only).
    Detailed component information is returned only when the caller provides a
    valid admin Bearer token, preventing reconnaissance by unauthenticated
    parties.  In debug mode full details are always returned for
    convenience.
    """
    from datetime import datetime

    from app.services.vectordb import get_vector_db

    overall_healthy = True

    # --- Run component checks (always, for status determination) ---

    # Vector DB
    vector_db_ok = True
    try:
        db = get_vector_db()
        if db is None:
            vector_db_ok = False
        else:
            await db.get_stats()
    except (ValueError, OSError, RuntimeError):
        vector_db_ok = False
        overall_healthy = False

    # Database
    db_ok = True
    try:
        from sqlalchemy import text

        from app.database import async_engine

        async def _db_probe() -> None:
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_db_probe(), timeout=_PROBE_TIMEOUT_SECONDS)
    except (OperationalError, DBAPIError, OSError) as e:
        logger.debug("Health check: database unreachable: %s", e)
        db_ok = False
        overall_healthy = False

    # Redis
    redis_ok = True
    redis_configured = bool(settings.redis_url)
    if redis_configured:
        try:
            # Sync client — run off the event loop with a hard bound.
            await asyncio.wait_for(asyncio.to_thread(_redis_ping), timeout=_PROBE_TIMEOUT_SECONDS)
        except (ValueError, OSError, RuntimeError):  # TimeoutError is an OSError
            redis_ok = False

    # LLM
    llm_configured = bool(settings.openai_api_key or settings.anthropic_api_key)
    if not llm_configured:
        overall_healthy = False

    status = "healthy" if overall_healthy else "degraded"

    # --- Determine if caller is authenticated admin ---
    is_admin = False
    if settings.debug:
        is_admin = True  # Always show details in local development
    else:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from app.services.auth import auth_service

                token_data = auth_service.verify_token(auth_header[7:])
                from app.utils.rbac import has_role as _has_role

                if _has_role("admin", token_data.roles):
                    is_admin = True
            except (JWTError, ValueError, KeyError, AttributeError):  # nosec B110 - auth failure just hides details
                pass

    # --- Build response ---
    response: dict = {
        "status": status,
        "timestamp": datetime.now(UTC).isoformat(),
        "version": APP_VERSION,
        "started_at": PROCESS_STARTED_AT,
    }

    if is_admin:
        # Detailed component breakdown (admin / dev only)
        response["environment"] = "production" if not settings.debug else "development"
        response["components"] = {
            "vector_db": {"healthy": vector_db_ok},
            "database": {"healthy": db_ok},
            "redis": {"healthy": redis_ok, "configured": redis_configured},
            "llm": {"configured": llm_configured},
        }

    return response


@router.get("/ready", response_model=ReadyResponse)
async def readiness_check() -> dict | JSONResponse:
    """
    Readiness check for Kubernetes.

    Returns 200 only when app is ready to serve traffic.
    Checks all required services are available.
    """
    issues = []
    # /ready is unauthenticated and both proxies expose it, so raw exception
    # text (driver errors, internal hostnames, Redis addresses) must not leak to
    # clients in production. Detail is logged; the response carries generic codes.
    expose_detail = settings.debug

    def _issue(label: str, err: Exception | None = None) -> str:
        if err is not None:
            logger.warning("Readiness check — %s: %s", label, err)
        return f"{label}: {err}" if (expose_detail and err is not None) else label

    # Check LLM provider
    if not settings.openai_api_key and not settings.anthropic_api_key:
        issues.append(_issue("No LLM provider configured (OPENAI_API_KEY or ANTHROPIC_API_KEY)"))

    # Check database connectivity
    try:
        from sqlalchemy import text

        from app.database import async_engine

        async def _db_probe() -> None:
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_db_probe(), timeout=_PROBE_TIMEOUT_SECONDS)
    except (OperationalError, DBAPIError, OSError) as e:
        issues.append(_issue("Database connection failed", e))

    # Check vector database
    try:
        from app.services.vectordb import get_vector_db

        db = get_vector_db()
        if db is not None:
            await db.get_stats()
        else:
            issues.append(_issue("Vector database not initialized"))
    except (ValueError, OSError, RuntimeError) as e:
        issues.append(_issue("Vector database failed", e))

    # Check Redis connectivity (required in production)
    if settings.redis_url and not settings.debug:
        try:
            # Sync client — run off the event loop with a hard bound.
            await asyncio.wait_for(asyncio.to_thread(_redis_ping), timeout=_PROBE_TIMEOUT_SECONDS)
        except (RedisError, ImportError, ValueError, ConnectionError, OSError, RuntimeError) as e:
            issues.append(_issue("Redis connection failed", e))

    if issues:
        return JSONResponse(
            status_code=503,
            content={"ready": False, "issues": issues},
        )

    return {"ready": True}


@router.get("/metrics", response_model=MetricsResponse)
async def metrics(request: Request) -> dict:
    """
    Prometheus-compatible metrics endpoint.

    Returns key application metrics for monitoring and alerting.
    Requires authentication in production mode.
    """
    # Require auth in production
    if not settings.debug:
        from app.services.auth import auth_service

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authentication required")
        try:
            token_data = auth_service.verify_token(auth_header[7:])
            from app.utils.rbac import has_role

            if not has_role("admin", token_data.roles):
                raise HTTPException(status_code=403, detail="Admin access required")
        except HTTPException:
            raise
        except (JWTError, ValueError, KeyError):
            raise HTTPException(status_code=401, detail="Invalid token")
    from datetime import datetime

    from app.services.documents import document_service
    from app.services.vectordb import get_vector_db

    metrics_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "application": {
            "name": settings.app_name,
            "version": "1.0.0",
            "environment": "production" if not settings.debug else "development",
        },
        "documents": {
            "total_count": len(document_service.documents),
            "indexed_count": sum(
                1 for d in document_service.documents.values() if d.status.value == "indexed"
            ),
            "failed_count": sum(
                1 for d in document_service.documents.values() if d.status.value == "failed"
            ),
            "total_chunks": sum(d.chunk_count for d in document_service.documents.values()),
        },
    }

    # Vector DB stats
    try:
        db = get_vector_db()
        if db is not None:
            db_stats = await db.get_stats()
            metrics_data["vector_db"] = {
                "type": settings.vector_db,
                "total_vectors": db_stats.get("total_chunks", 0),
                "healthy": True,
            }
        else:
            metrics_data["vector_db"] = {"healthy": False, "error": "not initialized"}
    except (ValueError, KeyError, ConnectionError, TimeoutError, OSError, RuntimeError) as e:
        metrics_data["vector_db"] = {"healthy": False, "error": str(e)}

    # Database stats
    try:
        from app.database import IS_POSTGRES, async_engine

        metrics_data["database"] = {
            "type": "postgresql" if IS_POSTGRES else "sqlite",
            "pool_size": async_engine.pool.size() if hasattr(async_engine.pool, "size") else "N/A",
        }
    except (AttributeError, ImportError, RuntimeError):
        metrics_data["database"] = {"type": "unknown"}

    # Redis stats (if configured)
    if settings.redis_url:
        try:
            # Sync client — run off the event loop with a hard bound.
            info = await asyncio.wait_for(
                asyncio.to_thread(_redis_memory_info), timeout=_PROBE_TIMEOUT_SECONDS
            )
            metrics_data["redis"] = {
                "connected": True,
                "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
            }
        except (RedisError, ImportError, ConnectionError, OSError):
            metrics_data["redis"] = {"connected": False}

    return metrics_data
