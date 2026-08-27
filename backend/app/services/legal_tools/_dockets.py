"""
Legal Tools - Docket search methods.
"""

import httpx

from app.services.courtlistener_gate import cl_client

from ._helpers import url_from_relative
from ._models import DocketResult


def _names(value) -> list[str]:
    """v4 docket search carries ``party`` / ``attorney`` as lists of names."""
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


class DocketsMixin:
    """Mixin providing docket search functionality."""

    async def search_dockets(
        self,
        query: str,
        court: str | None = None,
        party: str | None = None,
        limit: int = 20,
    ) -> list[DocketResult]:
        """
        Search court dockets.

        Args:
            query: Search terms
            court: Court ID
            party: Party name to search for
        """
        self._check_token()
        params = {
            "q": query,
            "type": "d",  # dockets
            "page_size": min(limit, 100),
        }

        if court:
            params["court"] = court
        if party:
            params["party_name"] = party

        async with cl_client(timeout=180.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/search/", params=params, headers=self.headers
            )
            response.raise_for_status()
            data = response.json()

        dockets = []
        for result in data.get("results", []):
            dockets.append(
                DocketResult(
                    id=result.get("docket_id") or result.get("id", 0),
                    case_name=result.get("caseName", "Unknown"),
                    case_name_full=result.get("case_name_full"),
                    docket_number=result.get("docketNumber", ""),
                    court=result.get("court", ""),
                    court_id=result.get("court_id"),
                    date_filed=self._parse_date(result.get("dateFiled")),
                    date_terminated=self._parse_date(result.get("dateTerminated")),
                    date_argued=self._parse_date(result.get("dateArgued")),
                    nature_of_suit=result.get("suitNature") or None,
                    cause=result.get("cause") or None,
                    jury_demand=result.get("juryDemand") or None,
                    jurisdiction_type=result.get("jurisdictionType") or None,
                    assigned_to=result.get("assignedTo") or None,
                    referred_to=result.get("referredTo") or None,
                    parties=[{"name": n} for n in _names(result.get("party"))],
                    attorneys=[{"name": n} for n in _names(result.get("attorney"))],
                    entry_count=result.get("entry_count", 0),
                    # v4 docket search exposes the page path as docket_absolute_url.
                    url=url_from_relative(
                        result.get("docket_absolute_url") or result.get("absolute_url")
                    )
                    or "https://www.courtlistener.com",
                )
            )

        return dockets

    async def get_docket_detail(self, docket_id: int) -> dict | None:
        """
        Full docket record for the in-app viewer: metadata, filing entries,
        and parties. Entries/parties exist only where RECAP has the data, so
        each section degrades to empty independently instead of failing the
        whole view.
        """
        self._check_token()

        async with cl_client(timeout=180.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/dockets/{docket_id}/", headers=self.headers
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            docket = response.json()

            entries: list[dict] = []
            entry_count = 0
            try:
                entries_resp = await client.get(
                    f"{self.BASE_URL}/docket-entries/",
                    params={
                        "docket": docket_id,
                        "order_by": "-date_filed",
                        "page_size": 100,
                    },
                    headers=self.headers,
                )
                entries_resp.raise_for_status()
                entries_data = entries_resp.json()
                entry_count = entries_data.get("count", 0)
                for e in entries_data.get("results", []):
                    description = e.get("description") or ""
                    docs = e.get("recap_documents") or []
                    if not description and docs and isinstance(docs[0], dict):
                        description = docs[0].get("description") or ""
                    # Free RECAP PDFs, when the archive has them.
                    documents = [
                        {
                            "description": d.get("description") or "",
                            "document_number": d.get("document_number"),
                            "page_count": d.get("page_count"),
                            "url": url_from_relative(d.get("filepath_local"))
                            if d.get("filepath_local")
                            else None,
                            "is_available": bool(d.get("is_available")),
                        }
                        for d in docs
                        if isinstance(d, dict)
                    ]
                    entries.append(
                        {
                            "entry_number": e.get("entry_number"),
                            "date_filed": e.get("date_filed"),
                            "description": description,
                            "documents": documents,
                        }
                    )
            except (httpx.HTTPError, ValueError, KeyError):
                pass

            parties: list[dict] = []
            try:
                parties_resp = await client.get(
                    f"{self.BASE_URL}/parties/",
                    params={"docket": docket_id, "page_size": 100},
                    headers=self.headers,
                )
                parties_resp.raise_for_status()
                for p in parties_resp.json().get("results", []):
                    types = p.get("party_types") or []
                    role = types[0].get("name") if types and isinstance(types[0], dict) else None
                    attorneys = [
                        a.get("name")
                        for a in (p.get("attorneys") or [])
                        if isinstance(a, dict) and a.get("name")
                    ]
                    parties.append({"name": p.get("name"), "role": role, "attorneys": attorneys})
            except (httpx.HTTPError, ValueError, KeyError):
                pass

            court_id = docket.get("court_id") or ""
            court_name = await self._court_name(client, court_id) if court_id else None

        return {
            "id": docket_id,
            "case_name": docket.get("case_name", "Unknown"),
            "case_name_full": docket.get("case_name_full") or None,
            "docket_number": docket.get("docket_number", ""),
            "court": court_id,
            "court_name": court_name,
            "date_filed": docket.get("date_filed"),
            "date_terminated": docket.get("date_terminated"),
            "date_last_filing": docket.get("date_last_filing"),
            "date_argued": docket.get("date_argued"),
            "assigned_to": docket.get("assigned_to_str") or None,
            "referred_to": docket.get("referred_to_str") or None,
            "nature_of_suit": docket.get("nature_of_suit") or None,
            "cause": docket.get("cause") or None,
            "jury_demand": docket.get("jury_demand") or None,
            "jurisdiction_type": docket.get("jurisdiction_type") or None,
            "pacer_case_id": docket.get("pacer_case_id") or None,
            "entries": entries,
            "entry_count": entry_count or len(entries),
            "parties": parties,
            "url": url_from_relative(docket.get("absolute_url")) or "https://www.courtlistener.com",
        }
