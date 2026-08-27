"""
Legal Tools - Legal trend analysis methods.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

import httpx

from app.services.courtlistener_gate import cl_client

logger = logging.getLogger(__name__)

# One CourtListener count-query per year (a 2000→now sweep is ~27 requests) —
# this is exactly the shape that trips CourtListener's rate limiter, so the
# sweep is polite (low concurrency, honors Retry-After) and complete results
# are cached so a re-run of the same topic never re-burns quota.
_TREND_CONCURRENCY = 3
_TREND_RETRIES = 3
_TREND_TIME_BUDGET = 55.0  # the whole sweep must beat the client's timeout
_TREND_CACHE_TTL = 15 * 60.0


class TrendsMixin:
    """Mixin providing legal trend analysis functionality."""

    async def analyze_legal_trend(
        self, topic: str, start_year: int = 2000, end_year: int = None
    ) -> dict[str, Any]:
        """
        Analyze how case law on a topic has evolved over time.

        Years are fetched concurrently, newest first — if the API rate-limits
        mid-sweep, the years that drop are the oldest, and the response says
        how many dropped instead of silently charting a partial series.
        429s are retried honoring Retry-After; complete sweeps are cached.
        """
        self._check_token()
        end_year = end_year or datetime.now().year

        cache: dict[tuple, tuple[float, dict[str, Any]]] = getattr(self, "_trend_cache", {})
        self._trend_cache = cache
        cache_key = (topic.strip().lower(), start_year, end_year)
        cached = cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < _TREND_CACHE_TTL:
            return cached[1]

        years_data: dict[int, int] = {}
        semaphore = asyncio.Semaphore(_TREND_CONCURRENCY)

        async with cl_client(timeout=30.0) as client:

            async def count_year(year: int) -> None:
                async with semaphore:
                    backoff = 1.0
                    for attempt in range(_TREND_RETRIES):
                        try:
                            response = await client.get(
                                f"{self.BASE_URL}/search/",
                                params={
                                    "q": topic,
                                    "type": "o",
                                    "filed_after": f"{year}-01-01",
                                    "filed_before": f"{year}-12-31",
                                    "page_size": 1,  # Just need count
                                },
                                headers=self.headers,
                            )
                        except (httpx.HTTPError, OSError) as e:
                            logger.warning(f"Trend count failed for {year}: {e}")
                            return
                        if response.status_code == 200:
                            years_data[year] = response.json().get("count", 0)
                            return
                        if response.status_code == 429 and attempt < _TREND_RETRIES - 1:
                            retry_after = response.headers.get("Retry-After")
                            try:
                                wait = min(float(retry_after), 10.0) if retry_after else backoff
                            except ValueError:
                                wait = backoff
                            await asyncio.sleep(wait)
                            backoff *= 2
                            continue
                        logger.warning(f"Trend count for {year} got HTTP {response.status_code}")
                        return

            # Newest years first: they matter most if anything gets cut off.
            try:
                await asyncio.wait_for(
                    asyncio.gather(*(count_year(y) for y in range(end_year, start_year - 1, -1))),
                    timeout=_TREND_TIME_BUDGET,
                )
            except TimeoutError:
                logger.warning("Trend sweep hit its time budget; returning completed years")

        failed_years = [y for y in range(start_year, end_year + 1) if y not in years_data]

        # Convert to array format for frontend
        years_array = [{"year": year, "count": count} for year, count in sorted(years_data.items())]

        # The current year is still being decided — it is always an undercount,
        # so it must not drive the direction.
        current_year = datetime.now().year
        current_year_partial = end_year >= current_year and current_year in years_data
        complete = [
            y for y in years_array if not (current_year_partial and y["year"] == current_year)
        ]
        first_year = complete[0]["year"] if complete else start_year
        last_year = complete[-1]["year"] if complete else end_year
        first_count = years_data.get(first_year, 0)
        last_count = years_data.get(last_year, 0)
        if len(complete) < 2:
            trend = "insufficient"
        elif last_count > first_count * 1.05:
            trend = "increasing"
        elif last_count < first_count * 0.95:
            trend = "decreasing"
        else:
            trend = "stable"
        result = {
            "topic": topic,
            "start_year": start_year,
            "end_year": end_year,
            "years": years_array,  # Array format for frontend charts
            "cases_by_year": years_data,  # Keep dict for backward compat
            "years_failed": len(failed_years),
            "total_cases": sum(years_data.values()),
            "trend": trend,
            "trend_basis": {"from_year": first_year, "to_year": last_year},
            "current_year_partial": current_year_partial,
        }
        # Only complete sweeps are worth remembering — a rate-limited partial
        # result must not be served for the next 15 minutes.
        if not failed_years and years_array:
            cache[cache_key] = (time.monotonic(), result)
        return result
