"""Judge intelligence response models — profiles, opinions, metrics."""

from typing import Any

from pydantic import BaseModel


class JudgeSearchResponse(BaseModel):
    """GET /judge-intel/search."""

    judges: list[dict[str, Any]]
    count: int
    total_available: int


class JudgeBuildResponse(BaseModel):
    """POST /judge-intel/build/{judge_id}."""

    status: str
    message: str
    profile: dict[str, Any]


class JudgeDeleteResponse(BaseModel):
    """DELETE /judge-intel/profile/{judge_id}."""

    status: str
    message: str


class JudgeProfileResponse(BaseModel):
    """GET /judge-intel/profile/{judge_id}."""

    class Config:
        extra = "allow"


class JudgeOpinionsResponse(BaseModel):
    """GET /judge-intel/profile/{judge_id}/opinions."""

    class Config:
        extra = "allow"


class JudgeOpinionTextResponse(BaseModel):
    """GET /judge-intel/profile/{judge_id}/opinion/{opinion_id}."""

    class Config:
        extra = "allow"


class JudgeStatsResponse(BaseModel):
    """GET /judge-intel/profile/{judge_id}/stats."""

    class Config:
        extra = "allow"


class JudgeMetricsResponse(BaseModel):
    """GET /judge-intel/profile/{judge_id}/metrics."""

    class Config:
        extra = "allow"
