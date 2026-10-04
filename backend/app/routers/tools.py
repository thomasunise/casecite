"""
Legal Research Tools API Routes

Provides endpoints for:
- Case Search
- Citation Validator
- Precedent Finder
- Docket Search
- Oral Arguments
- Legal Trends
"""

import logging
import time
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.auth import TokenData
from app.services.courtlistener import courtlistener_service
from app.services.courtlistener_errors import RESEARCH_ERRORS, courtlistener_http_error
from app.services.legal_tools import legal_tools
from app.services.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["legal-tools"])

# Threshold in seconds before showing slow API warning
SLOW_API_THRESHOLD = 10


def add_api_timing(result: dict[str, Any], elapsed_seconds: float) -> dict[str, Any]:
    """Add API timing info and slow warning to response."""
    result["_api_timing"] = {
        "elapsed_seconds": round(elapsed_seconds, 2),
        "is_slow": elapsed_seconds > SLOW_API_THRESHOLD,
    }
    if elapsed_seconds > SLOW_API_THRESHOLD:
        result["_api_warning"] = (
            f"CourtListener API is responding slowly ({round(elapsed_seconds, 1)}s). "
            "This is a third-party service issue, not a problem with our platform. "
            "Please be patient or try again later."
        )
    return result


_tool_error = courtlistener_http_error
_TOOL_ERRORS = RESEARCH_ERRORS


def _citing_case(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": c.get("id"),
        "case_name": c.get("case_name"),
        "citation": (c.get("citation") or [None])[0] if c.get("citation") else None,
        "court": c.get("court"),
        "date_filed": c["date_filed"].isoformat()
        if isinstance(c.get("date_filed"), date)
        else c.get("date_filed"),
        "treatment": getattr(c.get("treatment"), "value", c.get("treatment")),
        "snippet": c.get("snippet"),
        "context_found": c.get("context_found", False),
        "url": c.get("url"),
    }


def safe_dump(model):
    """Safely dump a pydantic model with JSON-compatible types."""
    if model is None:
        return None
    data = model.model_dump()

    # Citation validation: the UI shows counts in the summary grid and the
    # actual citing cases below it, so collapse the lists to counts AND keep
    # the cases (negative first, then caution, then positive).
    if "negative_citations" in data and isinstance(data["negative_citations"], list):
        neg = data["negative_citations"]
        cau = (
            data.get("caution_citations") if isinstance(data.get("caution_citations"), list) else []
        )
        pos = (
            data.get("positive_citations")
            if isinstance(data.get("positive_citations"), list)
            else []
        )
        data["citing_cases"] = [_citing_case(c) for c in (neg + cau + pos)][:60]
        data["negative_citations"] = len(neg)
        data["caution_citations"] = len(cau)
        data["positive_citations"] = len(pos)

    # Convert date objects to strings
    result = {}
    for key, value in data.items():
        if isinstance(value, date):
            result[key] = value.isoformat()
        elif isinstance(value, list):
            result[key] = []
            for item in value:
                if isinstance(item, dict):
                    clean_item = {}
                    for k, v in item.items():
                        if isinstance(v, date):
                            clean_item[k] = v.isoformat()
                        else:
                            clean_item[k] = v
                    result[key].append(clean_item)
                else:
                    result[key].append(item)
        else:
            result[key] = value
    return result


# ==================== CASE SEARCH (with pagination) ====================


@router.get("/cases/search")
async def search_cases(
    q: str = Query(..., description="Search query"),
    cursor: str | None = Query(None, description="Cursor for pagination (from next_cursor)"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    current_user: TokenData = require_permission("tools.research"),
) -> dict:
    """
    Search for cases with cursor-based pagination.
    Returns multiple results - scroll through thousands of cases.
    Use next_cursor from response to load more results.
    """
    try:
        start_time = time.time()
        result = await legal_tools.search_cases(q, cursor, page_size)
        elapsed = time.time() - start_time
        return add_api_timing(result, elapsed)
    except _TOOL_ERRORS as e:
        raise _tool_error(e, "Case search error", "Search failed. Please try again.")


@router.get("/cases/{opinion_id}")
async def get_case_detail(
    opinion_id: int,
    current_user: TokenData = require_permission("tools.research"),
) -> dict:
    """
    Get full case details including opinion text.
    Shows everything inline - no need to leave the app.
    """
    try:
        start_time = time.time()
        result = await legal_tools.get_case_detail(opinion_id)
        elapsed = time.time() - start_time
        if not result:
            raise HTTPException(status_code=404, detail="Case not found")
        return add_api_timing(result, elapsed)
    except HTTPException:
        raise
    except _TOOL_ERRORS as e:
        raise _tool_error(e, "Case detail error", "Failed to load case. Please try again.")


# ==================== CITATION VALIDATOR ====================


@router.get("/validate-citation")
async def validate_citation(
    citation: str = Query(..., description="Citation to validate, e.g., '410 U.S. 113'"),
    current_user: TokenData = require_permission("tools.research"),
) -> dict:
    """
    Scan citing opinions for treatment language near a citation.

    A citing-language scan over CourtListener search results, not an
    editorial citator (Shepard's/KeyCite). Returns:
    - warning_level: none / caution / warning / danger / unknown
    - is_good_law: true only for a clean read, null when undetermined, never false
    - Citing opinions grouped by the language found near the citation
    - Total citation count
    """
    try:
        start_time = time.time()
        result = await courtlistener_service.validate_citation(citation)
        elapsed = time.time() - start_time
        return add_api_timing(safe_dump(result), elapsed)
    except _TOOL_ERRORS as e:
        raise _tool_error(e, "Citation validation error", "Validation failed. Please try again.")


# ==================== PRECEDENT FINDER ====================


@router.get("/precedents")
async def find_precedents_get(
    topic: str = Query(..., description="Legal topic to search"),
    jurisdiction: str | None = Query(None, description="e.g., 'scotus', 'ca9', 'federal'"),
    min_citations: int = Query(5, ge=0, le=1_000_000, description="Minimum citation count"),
    limit: int = Query(20, ge=1, le=100),
    current_user: TokenData = require_permission("tools.research"),
) -> dict:
    """GET version of precedent finder."""
    try:
        start_time = time.time()
        results = await legal_tools.find_precedents(topic, jurisdiction, min_citations, limit)
        elapsed = time.time() - start_time
        result = {"precedents": [safe_dump(r) for r in results], "count": len(results)}
        return add_api_timing(result, elapsed)
    except _TOOL_ERRORS as e:
        raise _tool_error(e, "Precedent search error", "Search failed. Please try again.")


# ==================== DOCKET SEARCH ====================


@router.get("/dockets")
async def search_dockets_get(
    query: str = Query(..., description="Search terms"),
    court: str | None = Query(None, description="Court ID"),
    party: str | None = Query(None, description="Party name"),
    limit: int = Query(20, ge=1, le=100),
    current_user: TokenData = require_permission("tools.research"),
) -> dict:
    """GET version of docket search."""
    try:
        start_time = time.time()
        results = await legal_tools.search_dockets(query, court, party, limit)
        elapsed = time.time() - start_time
        result = {"dockets": [safe_dump(d) for d in results], "count": len(results)}
        return add_api_timing(result, elapsed)
    except _TOOL_ERRORS as e:
        raise _tool_error(e, "Docket search error", "Search failed. Please try again.")


@router.get("/dockets/{docket_id}")
async def get_docket_detail(
    docket_id: int,
    current_user: TokenData = require_permission("tools.research"),
) -> dict:
    """Full docket record for the in-app viewer: metadata, entries, parties."""
    try:
        start_time = time.time()
        result = await legal_tools.get_docket_detail(docket_id)
        elapsed = time.time() - start_time
        if result is None:
            raise HTTPException(status_code=404, detail="Docket not found")
        return add_api_timing(result, elapsed)
    except HTTPException:
        raise
    except _TOOL_ERRORS as e:
        raise _tool_error(e, "Docket detail error", "Failed to load docket. Please try again.")


# ==================== ORAL ARGUMENTS ====================


@router.get("/oral-arguments")
async def search_oral_arguments(
    query: str = Query(..., description="Search terms"),
    court: str | None = Query(None, description="Court ID (e.g., 'scotus')"),
    limit: int = Query(50, ge=1, le=100),
    current_user: TokenData = require_permission("tools.research"),
) -> dict:
    """
    Search oral argument recordings.

    Listen to actual Supreme Court arguments and more.
    """
    try:
        start_time = time.time()
        results = await legal_tools.search_oral_arguments(query, court, limit)
        elapsed = time.time() - start_time
        result = {"arguments": results, "count": len(results)}
        return add_api_timing(result, elapsed)
    except _TOOL_ERRORS as e:
        raise _tool_error(e, "Oral arguments search error", "Search failed. Please try again.")


# ==================== LEGAL TRENDS ====================


@router.get("/trends")
async def analyze_trend_get(
    topic: str = Query(..., description="Legal topic"),
    start_year: int = Query(2000, ge=1600, le=2200, description="Start year"),
    end_year: int | None = Query(None, ge=1600, le=2200, description="End year (default: current)"),
    current_user: TokenData = require_permission("tools.research"),
) -> dict:
    """GET version of trend analysis."""
    try:
        start_time = time.time()
        result = await legal_tools.analyze_legal_trend(topic, start_year, end_year)
        elapsed = time.time() - start_time
        return add_api_timing(result, elapsed)
    except _TOOL_ERRORS as e:
        raise _tool_error(e, "Trend analysis error", "Analysis failed. Please try again.")
