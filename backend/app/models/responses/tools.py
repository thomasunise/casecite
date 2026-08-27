"""Legal tools response models — CourtListener API wrappers."""

from typing import Any

from pydantic import BaseModel


class PrecedentListResponse(BaseModel):
    """GET /tools/precedents."""

    precedents: list[dict[str, Any]]
    count: int
    _api_timing: dict[str, Any] | None = None


class DocketListResponse(BaseModel):
    """GET /tools/dockets."""

    dockets: list[dict[str, Any]]
    count: int
    _api_timing: dict[str, Any] | None = None


class OralArgumentListResponse(BaseModel):
    """GET /tools/oral-arguments."""

    arguments: list[dict[str, Any]]
    count: int
    _api_timing: dict[str, Any] | None = None
