"""
Legal Tools - Precedent finder methods.
"""

from app.services.courtlistener_gate import cl_client

from ._helpers import (
    first_opinion_id,
    nested_snippet,
    order_citations,
    strip_marks,
    url_from_relative,
)
from ._models import PrecedentResult


class PrecedentsMixin:
    """Mixin providing precedent search functionality."""

    async def find_precedents(
        self,
        topic: str,
        jurisdiction: str | None = None,
        min_citations: int = 5,
        limit: int = 20,
    ) -> list[PrecedentResult]:
        """
        Find the most-cited cases on a topic.

        Args:
            topic: Legal topic or search terms
            jurisdiction: e.g., "scotus", "ca9", "federal"
            min_citations: Minimum citation count
            limit: Max results
        """
        self._check_token()
        params = {
            "q": topic,
            "type": "o",
            "cited_gt": min_citations,
            "order_by": "citeCount desc",  # Most cited first
            "page_size": min(limit, 100),
            "highlight": "on",
        }

        if jurisdiction:
            court_ids = self._get_courts_for_jurisdiction(jurisdiction)
            if court_ids:
                params["court"] = ",".join(court_ids)

        async with cl_client(timeout=180.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/search/", params=params, headers=self.headers
            )
            response.raise_for_status()
            data = response.json()

        precedents = []
        for result in data.get("results", []):
            citations = order_citations(result.get("citation") or [])
            precedents.append(
                PrecedentResult(
                    # V4 search reports the case under cluster_id (same mapping
                    # case lookup uses) — the row id 404s against the detail
                    # endpoint.
                    id=result.get("cluster_id") or result.get("id", 0),
                    opinion_id=first_opinion_id(result),
                    case_name=strip_marks(result.get("caseName")) or "Unknown",
                    citation=citations[0] if citations else "No citation",
                    citations=citations,
                    court=result.get("court", ""),
                    court_id=result.get("court_id"),
                    date_filed=self._parse_date(result.get("dateFiled")),
                    docket_number=strip_marks(result.get("docketNumber")) or None,
                    judges=strip_marks(result.get("judge")) or None,
                    status=result.get("status"),
                    times_cited=result.get("citeCount", 0),
                    snippet=nested_snippet(result) or None,
                    url=url_from_relative(result.get("absolute_url"))
                    or "https://www.courtlistener.com",
                )
            )

        return precedents
