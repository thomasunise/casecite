"""Job management response models — status, cancel, listing."""

from typing import Any

from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    """GET /jobs/{job_id} — poll job status and result."""

    class Config:
        extra = "allow"


class JobCancelledResponse(BaseModel):
    """DELETE /jobs/{job_id}."""

    status: str
    job_id: str


class JobListResponse(BaseModel):
    """GET /jobs."""

    jobs: list[dict[str, Any]]
    count: int
