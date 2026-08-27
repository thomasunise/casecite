"""System response models — health, readiness, metrics."""

from typing import Any

from pydantic import BaseModel


class SystemRootResponse(BaseModel):
    """GET / — API root info."""

    name: str
    version: str
    status: str
    docs: str


class HealthResponse(BaseModel):
    """GET /health."""

    status: str
    timestamp: str
    version: str | None = None
    started_at: str | None = None
    environment: str | None = None
    components: dict[str, Any] | None = None


class ReadyResponse(BaseModel):
    """GET /ready."""

    ready: bool
    issues: list[str] | None = None


class MetricsResponse(BaseModel):
    """GET /metrics."""

    timestamp: str
    application: dict[str, Any]
    documents: dict[str, Any]
    vector_db: dict[str, Any]
    database: dict[str, Any]
    # Only present when REDIS_URL is configured
    redis: dict[str, Any] | None = None
