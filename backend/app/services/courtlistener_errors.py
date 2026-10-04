"""
Map CourtListener / research-service failures to HTTP errors the UI can explain.

A rejected token, a rate limit and an upstream outage call for three different
user actions; none of them is a generic "Operation failed".
"""

from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

TOKEN_HELP = (
    "CourtListener rejected the configured API token. An admin can set a valid token under "
    "Settings → Integrations (or COURTLISTENER_API_TOKEN in the environment)."
)

# Everything a CourtListener-backed service call is expected to raise.
RESEARCH_ERRORS = (
    httpx.HTTPError,
    ValueError,
    KeyError,
    ConnectionError,
    TimeoutError,
    OSError,
    RuntimeError,
)


def courtlistener_http_error(e: Exception, label: str, fallback: str) -> HTTPException:
    """Return (not raise) the HTTPException for a failed research call."""
    logger.error(f"{label}: {e}", exc_info=True)
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code in (401, 403):
            return HTTPException(status_code=502, detail=TOKEN_HELP)
        if code == 429:
            return HTTPException(
                status_code=503,
                detail="CourtListener is rate-limiting requests right now. Wait a minute and try again.",
            )
        if code == 404:
            return HTTPException(status_code=404, detail="Not found on CourtListener.")
        return HTTPException(
            status_code=502, detail=f"CourtListener returned HTTP {code}. {fallback}"
        )
    if isinstance(e, httpx.TimeoutException | TimeoutError):
        return HTTPException(
            status_code=504, detail="CourtListener did not respond in time. Try again."
        )
    if isinstance(e, ValueError) and "token" in str(e).lower():
        return HTTPException(status_code=503, detail=str(e))
    return HTTPException(status_code=500, detail=fallback)
