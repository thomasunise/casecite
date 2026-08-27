"""
Judge Intelligence API Routes

Provides endpoints for comprehensive judge research:
- Search for judges
- Build complete intelligence profile
- Query opinions with filters
- Get statistics and metrics
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.models.responses.judge_intel import (
    JudgeBuildResponse,
    JudgeDeleteResponse,
    JudgeMetricsResponse,
    JudgeOpinionsResponse,
    JudgeOpinionTextResponse,
    JudgeProfileResponse,
    JudgeSearchResponse,
    JudgeStatsResponse,
)
from app.services.auth import TokenData, UserRole, require_roles
from app.services.courtlistener_errors import RESEARCH_ERRORS, courtlistener_http_error
from app.services.job_queue import RETRY_POLICIES, job_manager
from app.services.judge_intel import judge_intel
from app.services.permissions import require_permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/judge-intel", tags=["judge-intelligence"])


@router.get("/search", response_model=JudgeSearchResponse)
async def search_judges(
    q: str = Query(..., description="Judge name to search"),
    limit: int = Query(500, le=1000),
    current_user: TokenData = require_permission("judge_intel.use"),
) -> JudgeSearchResponse:
    """Search for judges by name. Returns up to 1000 matching judges. Requires authentication."""
    try:
        result = await judge_intel.search_judges(q, limit)
        return {
            "judges": result["judges"],
            "count": result["count"],
            "total_available": result["total_available"],
        }
    except RESEARCH_ERRORS as e:
        raise courtlistener_http_error(
            e, "Judge search error", "Operation failed. Please try again."
        )


@router.post("/build/{judge_id}", response_model=JudgeBuildResponse)
async def build_judge_intel(
    judge_id: int,
    force_refresh: bool = False,
    current_user: TokenData = require_permission("judge_intel.use"),
    async_mode: bool = Query(False, alias="async"),
) -> JudgeBuildResponse:
    """
    Build intelligence profile for a judge. Requires authentication.

    Optimized for speed:
    - Pulls up to 300 opinions (metadata)
    - Full text for top 25 most cited opinions
    - Up to 100 recent dockets
    - Typically completes in 30-60 seconds

    Use force_refresh=true to rebuild an existing profile.
    """

    user_id = current_user.user_id

    # Check cache eagerly (fast, avoids unnecessary async job)
    if not force_refresh and await judge_intel.is_judge_cached(judge_id):
        profile = await judge_intel.get_judge_profile(judge_id)
        return {
            "status": "cached",
            "message": "Judge data already exists in database. Use force_refresh=true to rebuild.",
            "profile": profile,
        }

    async def do_work():
        logger.info(f"Building judge profile for ID {judge_id} (user: {user_id})")
        # No timeout in either mode: the build makes 100+ CourtListener calls
        # deliberately paced by the shared gate (no bursts), so a prolific
        # judge legitimately takes minutes. The UI streams progress; killing
        # the build partway just wastes everything already fetched.
        profile = await judge_intel.build_judge_intel(judge_id)
        logger.info(f"Successfully built judge profile for ID {judge_id}")
        return {
            "status": "complete",
            "message": "Judge intelligence profile built successfully",
            "profile": profile,
        }

    if async_mode:
        job_id = await job_manager.submit(
            do_work,
            user_id=user_id,
            endpoint="/judge-intel/build",
            retry_policy=RETRY_POLICIES["external_api"],
        )
        return JSONResponse(
            status_code=202,
            content={"job_id": job_id, "poll_url": f"/api/v1/jobs/{job_id}"},
        )

    try:
        return await do_work()
    except ValueError as e:
        if "token" in str(e).lower():
            raise courtlistener_http_error(e, f"Build intel error for judge {judge_id}", "")
        logger.warning(f"Judge not found for build: {e}")
        raise HTTPException(status_code=404, detail="Judge not found")
    except HTTPException:
        raise
    except RESEARCH_ERRORS as e:
        raise courtlistener_http_error(
            e, f"Build intel error for judge {judge_id}", "Operation failed. Please try again."
        )


@router.get("/profile/{judge_id}", response_model=JudgeProfileResponse)
async def get_judge_profile(
    judge_id: int, current_user: TokenData = require_permission("judge_intel.use")
) -> JudgeProfileResponse:
    """Get complete judge profile from local database. Requires authentication."""
    try:
        profile = await judge_intel.get_judge_profile(judge_id)
        if not profile:
            raise HTTPException(
                status_code=404,
                detail="Judge not found in local database. Use /build first.",
            )
        return profile
    except HTTPException:
        raise
    except RESEARCH_ERRORS as e:
        raise courtlistener_http_error(
            e, "Profile error for judge {judge_id}", "Operation failed. Please try again."
        )


@router.get("/profile/{judge_id}/opinions", response_model=JudgeOpinionsResponse)
async def query_opinions(
    judge_id: int,
    q: str | None = Query(None, description="Search in case name or text"),
    court: str | None = Query(None, description="Filter by court"),
    year_start: int | None = Query(None, description="Start year"),
    year_end: int | None = Query(None, description="End year"),
    min_citations: int | None = Query(None, description="Minimum citations"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    order: str = Query("date", pattern="^(date|citations)$"),
    current_user: TokenData = require_permission("judge_intel.use"),
) -> JudgeOpinionsResponse:
    """Query judge's opinions with filters. Requires authentication."""
    try:
        results = await judge_intel.query_opinions(
            judge_id=judge_id,
            query=q,
            court=court,
            year_start=year_start,
            year_end=year_end,
            min_citations=min_citations,
            limit=limit,
            offset=offset,
            order=order,
        )
        return results
    except RESEARCH_ERRORS as e:
        raise courtlistener_http_error(
            e, "Query opinions error for judge {judge_id}", "Operation failed. Please try again."
        )


@router.get("/profile/{judge_id}/opinion/{opinion_id}", response_model=JudgeOpinionTextResponse)
async def get_opinion_full_text(
    judge_id: int, opinion_id: int, current_user: TokenData = require_permission("judge_intel.use")
) -> JudgeOpinionTextResponse:
    """Get full text of a specific opinion. Requires authentication."""
    try:
        opinion = await judge_intel.get_opinion_full_text(judge_id, opinion_id)
        if not opinion:
            raise HTTPException(status_code=404, detail="Opinion not found")
        return opinion
    except HTTPException:
        raise
    except RESEARCH_ERRORS as e:
        raise courtlistener_http_error(
            e, "Opinion error for {opinion_id}", "Operation failed. Please try again."
        )


@router.get("/profile/{judge_id}/stats", response_model=JudgeStatsResponse)
async def get_statistics(
    judge_id: int, current_user: TokenData = require_permission("judge_intel.use")
) -> JudgeStatsResponse:
    """Get comprehensive statistics for a judge. Requires authentication."""
    try:
        stats = await judge_intel.get_statistics(judge_id)
        return stats
    except RESEARCH_ERRORS as e:
        raise courtlistener_http_error(
            e, "Stats error for judge {judge_id}", "Operation failed. Please try again."
        )


@router.get("/profile/{judge_id}/metrics", response_model=JudgeMetricsResponse)
async def get_advanced_metrics(
    judge_id: int,
    force_recompute: bool = False,
    current_user: TokenData = require_permission("judge_intel.use"),
) -> JudgeMetricsResponse:
    """
    Get advanced metrics with full methodology explanations. Requires authentication.

    Returns computed metrics including:
    - Dissent/concurrence rates
    - Citation impact score
    - Case disposition time
    - Case type expertise
    - Writing complexity analysis
    - Opinion length trends
    - Political alignment indicator
    - Bench experience
    - Party win rates
    - Data completeness score

    Each metric includes:
    - Current value and supporting data
    - Data quality indicator (good/limited/insufficient)
    - Full methodology explanation (how it's calculated)
    - Limitations and caveats
    - Interpretation guidance

    Use force_recompute=true to recalculate (otherwise cached for 24h).
    """
    try:
        metrics = await judge_intel.get_judge_metrics_with_explanations(judge_id, force_recompute)
        if not metrics:
            raise HTTPException(
                status_code=404,
                detail="Judge not found in local database. Use /build first.",
            )
        return metrics
    except HTTPException:
        raise
    except RESEARCH_ERRORS as e:
        raise courtlistener_http_error(
            e, "Metrics error for judge {judge_id}", "Operation failed. Please try again."
        )


@router.delete("/profile/{judge_id}", response_model=JudgeDeleteResponse)
async def delete_judge_data(
    judge_id: int, current_user: TokenData = require_roles(UserRole.ADMIN)
) -> JudgeDeleteResponse:
    """Delete cached data for a judge (to refresh). Admin only."""
    try:
        await judge_intel.delete_judge_cache(judge_id)

        logger.info(f"Deleted judge data for ID {judge_id} (user: {current_user.user_id})")
        return {
            "status": "deleted",
            "message": f"All data for judge {judge_id} has been deleted",
        }
    except RESEARCH_ERRORS as e:
        raise courtlistener_http_error(
            e, "Delete error for judge {judge_id}", "Operation failed. Please try again."
        )
