"""
Job Management Router

Provides endpoints for polling, cancelling, and listing
async jobs submitted via the ?async=true query parameter.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models.responses.jobs import (
    JobCancelledResponse,
    JobListResponse,
    JobStatusResponse,
)
from app.services.auth import TokenData, get_current_user
from app.services.job_queue import job_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> JobStatusResponse:
    """
    Poll job status and result.

    Returns job data including status, result (when completed),
    and error details (when failed).
    """
    data = job_manager.get_job(job_id, current_user.user_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return data


@router.delete("/{job_id}", response_model=JobCancelledResponse)
async def cancel_job(
    job_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> JobCancelledResponse:
    """Cancel a running or pending job."""
    success = await job_manager.cancel_job(job_id, current_user.user_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Job not found or cannot be cancelled",
        )
    return {"status": "cancelled", "job_id": job_id}


@router.get("", response_model=JobListResponse)
async def list_jobs(
    limit: int = Query(20, ge=1, le=100),
    current_user: TokenData = Depends(get_current_user),
) -> JobListResponse:
    """List the current user's recent jobs."""
    jobs = job_manager.list_user_jobs(current_user.user_id, limit=limit)
    return {"jobs": jobs, "count": len(jobs)}
