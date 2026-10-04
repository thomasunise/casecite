"""
Legal Tools - Case lookup methods.
"""

from typing import Any

from app.services.courtlistener import _html_to_text
from app.services.courtlistener_gate import cl_client

from ._helpers import (
    OPINION_TYPE_LABELS,
    citation_dict_to_string,
    first_opinion_id,
    nested_snippet,
    order_citations,
    strip_marks,
    trailing_id,
    url_from_relative,
)

# A cluster can carry a lead opinion plus concurrences and dissents; read
# them all (bounded) so the reader sees the whole decision, not just page one.
MAX_SUB_OPINIONS = 6
OPINION_TEXT_LIMIT = 50_000


class CaseLookupMixin:
    """Mixin providing case lookup functionality."""

    async def search_cases(
        self, query: str, cursor: str | None = None, page_size: int = 20
    ) -> dict[str, Any]:
        """
        Search for cases with cursor-based pagination (V4 API).
        Returns multiple results that users can scroll through.
        """
        self._check_token()

        async with cl_client(timeout=180.0) as client:
            if cursor:
                # Use cursor URL directly for pagination
                response = await client.get(cursor, headers=self.headers)
            else:
                # Initial search. highlight=on is what makes CourtListener fill
                # the (nested) snippet with the matching passage.
                response = await client.get(
                    f"{self.BASE_URL}/search/",
                    params={
                        "q": query,
                        "type": "o",
                        "page_size": min(page_size, 100),
                        "highlight": "on",
                    },
                    headers=self.headers,
                )
            if response.status_code == 403:
                raise ValueError("CourtListener API access denied. Check your API token.")
            response.raise_for_status()
            data = response.json()

        results = []
        for r in data.get("results", []):
            results.append(
                {
                    "id": r.get("cluster_id") or r.get("id"),  # V4 uses cluster_id
                    "opinion_id": first_opinion_id(r),
                    "case_name": strip_marks(r.get("caseName")) or "Unknown",
                    "case_name_short": strip_marks(r.get("caseNameShort")) or None,
                    "case_name_full": strip_marks(r.get("caseNameFull")) or None,
                    # Official reporter first; the UI shows the first entry.
                    "citation": order_citations(r.get("citation") or []),
                    "court": r.get("court", ""),
                    "court_id": r.get("court_id"),
                    "date_filed": r.get("dateFiled"),
                    "date_argued": r.get("dateArgued"),
                    "docket_number": strip_marks(r.get("docketNumber")) or None,
                    "judges": strip_marks(r.get("judge")) or None,
                    "status": r.get("status"),
                    "nature_of_suit": strip_marks(r.get("suitNature")) or None,
                    "snippet": nested_snippet(r),
                    "times_cited": r.get("citeCount", 0),
                    "url": url_from_relative(r.get("absolute_url")),
                }
            )

        return {
            "results": results,
            "count": data.get("count", 0),
            "next_cursor": data.get("next"),  # Full URL for next page
            "prev_cursor": data.get("previous"),
            "has_next": bool(data.get("next")),
            "has_prev": bool(data.get("previous")),
        }

    async def get_case_detail(self, case_id: int) -> dict[str, Any] | None:
        """
        Get full case details including opinion text.

        ``case_id`` is the CLUSTER id that search_cases returns (V4 search
        exposes cluster_id). We resolve the cluster, then every sub-opinion
        (lead, concurrences, dissents) for the readable text. For robustness
        we fall back to treating the id as an opinion id (older links / direct
        opinion ids) and follow its cluster.
        """
        self._check_token()

        async with cl_client(timeout=180.0) as client:
            # Primary path: treat the id as a cluster id (what search returns).
            cluster_data: dict[str, Any] = {}
            opinions_raw: list[dict[str, Any]] = []
            cluster_resp = await client.get(
                f"{self.BASE_URL}/clusters/{case_id}/", headers=self.headers
            )
            if cluster_resp.status_code == 403:
                raise ValueError("CourtListener API access denied. Check your API token.")
            if cluster_resp.status_code == 200:
                cluster_data = cluster_resp.json()
                for sub_url in (cluster_data.get("sub_opinions") or [])[:MAX_SUB_OPINIONS]:
                    op_resp = await client.get(sub_url, headers=self.headers)
                    if op_resp.status_code == 200:
                        opinions_raw.append(op_resp.json())
            else:
                # Fallback: maybe it's an opinion id — fetch it and its cluster.
                op_resp = await client.get(
                    f"{self.BASE_URL}/opinions/{case_id}/", headers=self.headers
                )
                if op_resp.status_code == 404:
                    return None
                if op_resp.status_code == 403:
                    raise ValueError("CourtListener API access denied. Check your API token.")
                op_resp.raise_for_status()
                opinions_raw.append(op_resp.json())
                cluster_url = opinions_raw[0].get("cluster")
                if cluster_url:
                    c_resp = await client.get(cluster_url, headers=self.headers)
                    if c_resp.status_code == 200:
                        cluster_data = c_resp.json()

            if not cluster_data and not opinions_raw:
                return None

            # The cluster does not carry the court or docket number — they live
            # on the docket record. One more request; both degrade to None.
            docket_number = None
            court_id = None
            court_name = ""
            docket_ref = cluster_data.get("docket")
            if isinstance(docket_ref, dict):
                docket_number = docket_ref.get("docket_number")
                court_id = docket_ref.get("court_id")
            elif isinstance(docket_ref, str) and docket_ref:
                try:
                    d_resp = await client.get(docket_ref, headers=self.headers)
                    if d_resp.status_code == 200:
                        d = d_resp.json()
                        docket_number = d.get("docket_number")
                        court_id = d.get("court_id") or trailing_id_str(d.get("court"))
                except Exception:  # docket is supplementary
                    pass
            if court_id:
                court_name = await self._court_name(client, court_id) or ""
            if not court_name and isinstance(cluster_data.get("court"), str):
                # Older payloads carried a court string directly.
                raw_court = cluster_data.get("court") or ""
                court_name = "" if raw_court.startswith("http") else raw_court

        # Readable text for display: many opinions (e.g. NY slip opinions)
        # carry an empty plain_text and only HTML — strip it to text, NEVER
        # hand raw markup to the UI.
        opinions: list[dict[str, Any]] = []
        for op in opinions_raw:
            text = op.get("plain_text") or _html_to_text(
                op.get("html_with_citations") or op.get("html")
            )
            type_code = op.get("type") or ""
            opinions.append(
                {
                    "id": op.get("id"),
                    "type": type_code,
                    "type_label": OPINION_TYPE_LABELS.get(type_code, "Opinion"),
                    "author": op.get("author_str") or None,
                    "per_curiam": bool(op.get("per_curiam")),
                    "text": (text or "")[:OPINION_TEXT_LIMIT],
                }
            )
        lead = opinions[0] if opinions else {}
        lead_raw = opinions_raw[0] if opinions_raw else {}
        html_text = lead_raw.get("html_with_citations") or lead_raw.get("html") or ""

        citations = [
            s
            for s in (citation_dict_to_string(c) for c in cluster_data.get("citations") or [])
            if s
        ]

        return {
            "id": case_id,
            "case_name": cluster_data.get("case_name", "Unknown"),
            "case_name_short": cluster_data.get("case_name_short"),
            "case_name_full": cluster_data.get("case_name_full"),
            "citations": order_citations(citations),
            "court": court_name,
            "court_id": court_id,
            "date_filed": cluster_data.get("date_filed"),
            "date_argued": cluster_data.get("date_argued"),
            "docket_number": docket_number,
            "judges": cluster_data.get("judges", ""),
            "nature_of_suit": cluster_data.get("nature_of_suit", ""),
            "posture": cluster_data.get("posture") or "",
            "opinion_text": lead.get("text", ""),
            "html_text": html_text[:100000] if html_text else "",
            "opinions": opinions,
            "syllabus": cluster_data.get("syllabus", ""),
            "headnotes": cluster_data.get("headnotes", ""),
            "summary": cluster_data.get("summary", ""),
            "times_cited": cluster_data.get("citation_count", 0),
            "precedential_status": cluster_data.get("precedential_status", ""),
            "url": url_from_relative(cluster_data.get("absolute_url")),
        }


def trailing_id_str(url: str | None) -> str | None:
    """``.../courts/scotus/`` → ``scotus`` (court ids are slugs, not ints)."""
    if not url or not isinstance(url, str):
        return None
    parts = [p for p in url.rstrip("/").split("/") if p]
    return parts[-1] if parts else None


__all__ = ["CaseLookupMixin", "trailing_id", "trailing_id_str"]
