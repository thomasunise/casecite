"""CourtListener API integration mixin for JudgeIntelService."""

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from app.services.courtlistener_gate import cl_client

logger = logging.getLogger(__name__)


class CourtListenerMixin:
    """CourtListener API methods: search, build profile, pull opinions/dockets/citations."""

    async def search_judges(self, query: str, limit: int = 500) -> dict[str, Any]:
        """
        Search for judges by name.
        Uses the /people/ endpoint with name filtering for accurate results.
        """
        self._check_token()

        judges = []
        next_url = None
        total_count = 0

        # Clean up the query
        query = query.strip()

        async with cl_client(timeout=60.0) as client:
            while len(judges) < limit:
                if next_url:
                    response = await client.get(next_url, headers=self.headers)
                else:
                    params = {
                        "page_size": 100,
                    }

                    query_parts = query.split()
                    if len(query_parts) >= 2:
                        params["name_first__icontains"] = query_parts[0]
                        params["name_last__icontains"] = query_parts[-1]
                    else:
                        params["name_last__icontains"] = query

                    response = await client.get(
                        f"{self.BASE_URL}/people/", params=params, headers=self.headers
                    )

                if response.status_code != 200:
                    response = await client.get(
                        f"{self.BASE_URL}/search/",
                        params={"q": f"name:{query}", "type": "p", "page_size": 100},
                        headers=self.headers,
                    )

                response.raise_for_status()
                data = response.json()

                if total_count == 0:
                    total_count = data.get("count", 0)

                results = data.get("results", [])
                if not results:
                    break

                for r in results:
                    if len(judges) >= limit:
                        break

                    name_first = r.get("name_first", "") or ""
                    name_middle = r.get("name_middle", "") or ""
                    name_last = r.get("name_last", "") or ""
                    name_suffix = r.get("name_suffix", "") or ""

                    full_name = " ".join(
                        filter(None, [name_first, name_middle, name_last, name_suffix])
                    ).strip()
                    if not full_name:
                        full_name = r.get("name_full") or r.get("name", "Unknown")

                    judges.append(
                        {
                            "id": r.get("id"),
                            "name": full_name,
                            "name_full": r.get("name_full") or full_name,
                            "name_first": name_first,
                            "name_last": name_last,
                            "court": r.get("court"),
                            "position": r.get("position_type"),
                            "appointed_by": r.get("appointer"),
                            "date_start": r.get("date_start"),
                            "dob": r.get("date_dob"),
                            "political_affiliation": r.get("political_affiliation"),
                            "url": f"https://www.courtlistener.com/person/{r.get('id')}/"
                            if r.get("id")
                            else "",
                        }
                    )

                next_url = data.get("next")
                if not next_url:
                    break
                # Validate pagination URL stays on courtlistener.com (SSRF prevention)
                from urllib.parse import urlparse as _urlparse

                if _urlparse(next_url).hostname not in (
                    "www.courtlistener.com",
                    "courtlistener.com",
                ):
                    logger.warning(f"Pagination URL left courtlistener.com domain: {next_url}")
                    break

                await asyncio.sleep(0.1)

            # If searching by last name only and we have room, also search first name
            if len(query.split()) == 1 and len(judges) < limit:
                try:
                    response = await client.get(
                        f"{self.BASE_URL}/people/",
                        params={"name_first__icontains": query, "page_size": 50},
                        headers=self.headers,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        existing_ids = {j["id"] for j in judges}

                        for r in data.get("results", []):
                            if len(judges) >= limit:
                                break
                            if r.get("id") in existing_ids:
                                continue

                            name_first = r.get("name_first", "") or ""
                            name_middle = r.get("name_middle", "") or ""
                            name_last = r.get("name_last", "") or ""
                            name_suffix = r.get("name_suffix", "") or ""

                            full_name = " ".join(
                                filter(
                                    None,
                                    [name_first, name_middle, name_last, name_suffix],
                                )
                            ).strip()
                            if not full_name:
                                full_name = r.get("name_full") or r.get("name", "Unknown")

                            judges.append(
                                {
                                    "id": r.get("id"),
                                    "name": full_name,
                                    "name_full": r.get("name_full") or full_name,
                                    "name_first": name_first,
                                    "name_last": name_last,
                                    "court": r.get("court"),
                                    "position": r.get("position_type"),
                                    "appointed_by": r.get("appointer"),
                                    "date_start": r.get("date_start"),
                                    "dob": r.get("date_dob"),
                                    "political_affiliation": r.get("political_affiliation"),
                                    "url": f"https://www.courtlistener.com/person/{r.get('id')}/"
                                    if r.get("id")
                                    else "",
                                }
                            )
                            total_count += 1
                except (httpx.HTTPError, KeyError, ValueError) as e:
                    logger.debug(f"First name search failed (non-critical): {e}")
                    pass  # First name search is supplementary, don't fail on errors

        # Sort results to prioritize exact matches. For "sonia sotomayor" the
        # last word is the surname and the first word the given name; a single
        # word is matched against both.
        query_lower = query.lower()
        words = query_lower.split()
        q_last = words[-1] if words else query_lower
        q_first = words[0] if len(words) >= 2 else None

        def sort_key(j):
            name = (j.get("name") or "").lower()
            name_last = (j.get("name_last") or "").lower()
            name_first = (j.get("name_first") or "").lower()
            first_ok = q_first is None or name_first.startswith(q_first)

            if name_last == q_last and (q_first is None or name_first == q_first):
                return (0, name)
            if name_last == q_last and first_ok:
                return (1, name)
            if name_last.startswith(q_last) and first_ok:
                return (2, name)
            if q_last in name_last:
                return (3, name)
            if name_first == q_last or name_first.startswith(q_last):
                return (4, name)
            return (5, name)

        judges.sort(key=sort_key)

        return {"judges": judges, "count": len(judges), "total_available": total_count}

    async def build_judge_intel(
        self, judge_id: int, progress_callback: Callable | None = None
    ) -> dict[str, Any]:
        """
        Build complete intelligence profile for a judge.
        Pulls ALL available data and stores in main database.

        Args:
            judge_id: CourtListener judge ID
            progress_callback: Optional callback for progress updates

        Returns:
            Complete judge profile with stats
        """
        self._check_token()

        def update_progress(msg):
            if progress_callback:
                progress_callback(msg)

        update_progress("Fetching judge biographical data...")

        # 1. Get full judge profile
        async with cl_client(timeout=60.0) as client:
            response = await client.get(f"{self.BASE_URL}/people/{judge_id}/", headers=self.headers)
            if response.status_code == 404:
                raise ValueError(f"Judge with ID {judge_id} not found")
            response.raise_for_status()
            api_judge_data = response.json()

        # 2. Fetch Wikipedia data
        judge_name = (
            f"{api_judge_data.get('name_first', '')} {api_judge_data.get('name_last', '')}".strip()
        )
        update_progress(f"Searching Wikipedia for {judge_name}...")
        wikipedia_data = await self.fetch_wikipedia_data(judge_name)

        # Helper to convert list values to comma-separated strings
        def to_string(val):
            if isinstance(val, list):
                return ", ".join(str(v) for v in val) if val else None
            return val

        # Build the judge_data dict
        judge_data = {
            "id": judge_id,
            "name": judge_name,
            "name_first": to_string(api_judge_data.get("name_first")),
            "name_middle": to_string(api_judge_data.get("name_middle")),
            "name_last": to_string(api_judge_data.get("name_last")),
            "name_suffix": to_string(api_judge_data.get("name_suffix")),
            "date_of_birth": to_string(api_judge_data.get("date_dob")),
            "place_of_birth_city": to_string(api_judge_data.get("dob_city")),
            "place_of_birth_state": to_string(api_judge_data.get("dob_state")),
            "date_of_death": to_string(api_judge_data.get("date_dod")),
            "gender": to_string(api_judge_data.get("gender")),
            "race": to_string(api_judge_data.get("race")),
            "religion": to_string(api_judge_data.get("religion")),
            "political_affiliation": to_string(api_judge_data.get("political_affiliation")),
            "aba_rating": to_string(api_judge_data.get("aba_rating")),
            "courtlistener_url": f"https://www.courtlistener.com/person/{judge_id}/",
            "data_pulled_at": datetime.now(UTC).isoformat(),
            "wikipedia_url": wikipedia_data.get("url"),
            "wikipedia_summary": wikipedia_data.get("summary"),
            "wikipedia_bio": wikipedia_data.get("bio"),
            "wikipedia_early_life": wikipedia_data.get("early_life"),
            "wikipedia_education": wikipedia_data.get("education"),
            "wikipedia_career": wikipedia_data.get("career"),
            "wikipedia_judicial_service": wikipedia_data.get("judicial_service"),
            "wikipedia_notable_cases": wikipedia_data.get("notable_cases"),
            "wikipedia_personal_life": wikipedia_data.get("personal_life"),
            "wikipedia_raw": wikipedia_data.get("raw"),
        }

        # 3. Process education - fetch from URLs if needed
        update_progress("Processing education history...")
        education_list = []
        educations = api_judge_data.get("educations", [])
        async with cl_client(timeout=30.0) as client:
            for edu in educations:
                edu_data = edu
                if isinstance(edu, str) and edu.startswith("http"):
                    try:
                        resp = await client.get(edu, headers=self.headers)
                        if resp.status_code == 200:
                            edu_data = resp.json()
                        else:
                            continue
                    except (
                        ValueError,
                        KeyError,
                        ConnectionError,
                        TimeoutError,
                        OSError,
                        RuntimeError,
                    ) as e:
                        logger.error(f"Error fetching education: {e}")
                        continue

                if not isinstance(edu_data, dict):
                    continue

                school = edu_data.get("school", {})
                if isinstance(school, str) and school.startswith("http"):
                    try:
                        resp = await client.get(school, headers=self.headers)
                        if resp.status_code == 200:
                            school = resp.json()
                    except (httpx.HTTPError, ValueError, KeyError):
                        pass

                education_list.append(
                    {
                        "school_name": school.get("name")
                        if isinstance(school, dict)
                        else str(school)
                        if school
                        else None,
                        "school_type": school.get("type") if isinstance(school, dict) else None,
                        "degree": edu_data.get("degree_level") or edu_data.get("degree_detail"),
                        "degree_year": edu_data.get("degree_year"),
                    }
                )

        judge_data["education"] = education_list

        # 4. Process positions - fetch from URLs if needed
        update_progress("Processing career history...")
        positions_list = []
        positions = api_judge_data.get("positions", [])
        async with cl_client(timeout=30.0) as client:
            for pos in positions:
                pos_data = pos
                if isinstance(pos, str) and pos.startswith("http"):
                    try:
                        resp = await client.get(pos, headers=self.headers)
                        if resp.status_code == 200:
                            pos_data = resp.json()
                        else:
                            continue
                    except (
                        ValueError,
                        KeyError,
                        ConnectionError,
                        TimeoutError,
                        OSError,
                        RuntimeError,
                    ) as e:
                        logger.error(f"Error fetching position: {e}")
                        continue

                if not isinstance(pos_data, dict):
                    continue

                court = pos_data.get("court", {})
                if isinstance(court, str) and court.startswith("http"):
                    try:
                        resp = await client.get(court, headers=self.headers)
                        if resp.status_code == 200:
                            court = resp.json()
                    except (httpx.HTTPError, ValueError, KeyError):
                        pass

                appointer = pos_data.get("appointer")
                if isinstance(appointer, str) and appointer.startswith("http"):
                    try:
                        resp = await client.get(appointer, headers=self.headers)
                        if resp.status_code == 200:
                            appointer_data = resp.json()
                            appointer = (
                                appointer_data.get("name_full")
                                or f"{appointer_data.get('name_first', '')} {appointer_data.get('name_last', '')}".strip()
                            )
                    except (httpx.HTTPError, ValueError, KeyError):
                        appointer = None

                positions_list.append(
                    {
                        "position_type": to_string(pos_data.get("position_type")),
                        "court_name": court.get("full_name") or court.get("short_name")
                        if isinstance(court, dict)
                        else str(court)
                        if court
                        else None,
                        "court_id": court.get("id") if isinstance(court, dict) else None,
                        "appointer": to_string(appointer)
                        if not isinstance(appointer, str) or not appointer.startswith("http")
                        else None,
                        "date_start": to_string(pos_data.get("date_start")),
                        "date_termination": to_string(pos_data.get("date_termination")),
                        "termination_reason": to_string(pos_data.get("termination_reason")),
                    }
                )

        judge_data["positions"] = positions_list

        # 5. Pull opinions
        update_progress("Fetching opinions (optimized - ~30 seconds)...")
        all_opinions = await self._pull_all_opinions(
            judge_id,
            judge_name,
            update_progress,
            max_opinions=300,
            fetch_full_text_count=25,
        )

        # 6. Pull assigned dockets/cases
        update_progress("Fetching recent assigned cases...")
        all_dockets = await self._pull_assigned_dockets(
            judge_id,
            judge_name,
            update_progress,
            max_dockets=100,
        )

        # 7. Pull citation relationship data
        update_progress("Analyzing citation patterns...")
        citations = await self._pull_citation_data(
            judge_id, all_opinions, update_progress, max_citations=100
        )

        # Build opinions_data
        opinions_data = {
            "opinions": all_opinions,
            "dockets": all_dockets,
            "citations": citations,
        }

        # Store everything in the cache
        await self._set_cache(judge_id, judge_data, opinions_data)

        # Return summary
        return await self.get_judge_profile(judge_id)

    async def _pull_all_opinions(
        self,
        judge_id: int,
        judge_name: str,
        progress_callback,
        max_opinions: int = 300,
        fetch_full_text_count: int = 25,
    ) -> list[dict]:
        """
        Pull opinions authored by this judge.

        Optimized for speed:
        - Limits total opinions (default 300)
        - Only fetches full text for top cited opinions (default 25)
        - Stores metadata for all, full text only for important ones
        """

        total_pulled = 0
        cursor_url = None
        all_opinions = []

        last_name = judge_name.split()[-1] if judge_name else ""
        progress_callback(f"Fetching opinion metadata (limit: {max_opinions})...")

        async with cl_client(timeout=60.0) as client:
            # Phase 1: Quickly pull opinion metadata
            while total_pulled < max_opinions:
                if cursor_url:
                    response = await client.get(cursor_url, headers=self.headers)
                else:
                    search_query = f'judge:"{judge_name}" OR judge:"{last_name}"'
                    response = await client.get(
                        f"{self.BASE_URL}/search/",
                        params={
                            "q": search_query,
                            "type": "o",
                            "page_size": 100,
                            "order_by": "dateFiled desc",
                        },
                        headers=self.headers,
                    )

                if response.status_code != 200:
                    break

                data = response.json()
                results = data.get("results", [])

                if not results:
                    break

                for r in results:
                    if total_pulled >= max_opinions:
                        break

                    opinion_id = r.get("cluster_id") or r.get("id")
                    citations = r.get("citation", [])
                    citation_str = citations[0] if citations else ""

                    opinion_data = {
                        "id": opinion_id,
                        "case_name": r.get("caseName", "Unknown"),
                        "case_name_short": r.get("caseNameShort"),
                        "court": r.get("court", ""),
                        "court_id": r.get("court_id", ""),
                        "date_filed": r.get("dateFiled"),
                        "date_argued": r.get("dateArgued"),
                        "docket_number": r.get("docketNumber"),
                        "citation": citation_str,
                        "citation_count": r.get("citeCount", 0),
                        "precedential_status": r.get("status"),
                        "opinion_type": r.get("type") or r.get("opinion_type"),
                        "per_curiam": 1 if r.get("per_curiam") else 0,
                        "url": f"https://www.courtlistener.com{r.get('absolute_url', '')}",
                        "snippet": r.get("snippet", "")[:500] if r.get("snippet") else "",
                        "full_text": "",
                        "word_count": 0,
                    }
                    all_opinions.append(opinion_data)
                    total_pulled += 1

                progress_callback(f"Found {total_pulled} opinions...")

                cursor_url = data.get("next")
                if not cursor_url or total_pulled >= max_opinions:
                    break
                # Validate pagination URL stays on courtlistener.com (SSRF prevention)
                from urllib.parse import urlparse as _urlparse

                if _urlparse(cursor_url).hostname not in (
                    "www.courtlistener.com",
                    "courtlistener.com",
                ):
                    logger.warning(f"Pagination URL left courtlistener.com domain: {cursor_url}")
                    break

                await asyncio.sleep(0.05)

            # Phase 2: Get full text for top cited opinions only
            if all_opinions and fetch_full_text_count > 0:
                sorted_opinions = sorted(
                    all_opinions, key=lambda x: x.get("citation_count", 0), reverse=True
                )
                top_opinions = sorted_opinions[:fetch_full_text_count]

                progress_callback(
                    f"Fetching full text for top {len(top_opinions)} cited opinions..."
                )

                for i, op in enumerate(top_opinions):
                    opinion_id = op["id"]
                    full_text = ""

                    try:
                        full_text, parts = await self._fetch_cluster_text(client, opinion_id)
                        op["opinion_parts"] = parts
                    except (
                        ValueError,
                        KeyError,
                        ConnectionError,
                        TimeoutError,
                        OSError,
                        RuntimeError,
                        httpx.HTTPError,
                    ) as e:
                        logger.error(f"Error fetching full text for opinion {opinion_id}: {e}")

                    op["full_text"] = full_text[:100000] if full_text else ""
                    op["word_count"] = len(full_text.split()) if full_text else 0

                    if (i + 1) % 5 == 0:
                        progress_callback(f"Fetched full text: {i + 1}/{len(top_opinions)}")

                    await asyncio.sleep(0.05)

        return all_opinions

    async def _fetch_cluster_text(
        self, client: Any, cluster_id: int, max_opinions: int = 6
    ) -> tuple[str, list[dict[str, Any]]]:
        """Readable text for every opinion in a cluster (lead, concurrences,
        dissents), with a heading per part when there is more than one.

        Most CourtListener opinions carry an empty ``plain_text`` and only
        ``html_with_citations`` — strip the HTML rather than reporting "no
        text". Returns ("", []) when the cluster has no text at all.
        """
        from app.services.courtlistener import _html_to_text
        from app.services.legal_tools._helpers import OPINION_TYPE_LABELS

        resp = await client.get(
            f"{self.BASE_URL}/clusters/{cluster_id}/", headers=self.headers, timeout=30.0
        )
        if resp.status_code != 200:
            return "", []
        subs = resp.json().get("sub_opinions") or []
        parts: list[str] = []
        meta: list[dict[str, Any]] = []
        for ref in subs[:max_opinions]:
            if isinstance(ref, dict):
                data = ref
            elif isinstance(ref, str) and ref.startswith("http"):
                r = await client.get(ref, headers=self.headers, timeout=20.0)
                if r.status_code != 200:
                    continue
                data = r.json()
            else:
                continue
            text = (
                data.get("plain_text")
                or _html_to_text(
                    data.get("html_with_citations")
                    or data.get("html")
                    or data.get("html_lawbox")
                    or data.get("html_columbia")
                    or data.get("xml_harvard")
                )
                or ""
            ).strip()
            if not text:
                continue
            label = OPINION_TYPE_LABELS.get(data.get("type") or "", "Opinion")
            author = (data.get("author_str") or "").strip()
            meta.append(
                {
                    "id": data.get("id"),
                    "type": data.get("type"),
                    "type_label": label,
                    "author": author or None,
                    "words": len(text.split()),
                }
            )
            header = f"{label} — {author}" if author else label
            parts.append(f"{header}\n\n{text}" if len(subs) > 1 else text)
        return "\n\n\n".join(parts), meta

    async def _pull_assigned_dockets(
        self,
        judge_id: int,
        judge_name: str,
        progress_callback,
        max_dockets: int = 100,
    ) -> list[dict]:
        """Pull dockets/cases assigned to this judge."""

        total_pulled = 0
        cursor_url = None
        all_dockets = []

        last_name = judge_name.split()[-1] if judge_name else ""

        async with cl_client(timeout=60.0) as client:
            while total_pulled < max_dockets:
                if cursor_url:
                    response = await client.get(cursor_url, headers=self.headers)
                else:
                    response = await client.get(
                        f"{self.BASE_URL}/search/",
                        params={
                            "q": f'assignedTo:"{judge_name}" OR assignedTo:"{last_name}"',
                            "type": "r",
                            "page_size": 100,
                            "order_by": "dateFiled desc",
                        },
                        headers=self.headers,
                    )

                if response.status_code != 200:
                    break

                data = response.json()
                results = data.get("results", [])

                if not results:
                    break

                for r in results:
                    docket_id = r.get("docket_id") or r.get("id")

                    try:
                        all_dockets.append(
                            {
                                "id": docket_id,
                                "judge_id": judge_id,
                                "case_name": r.get("caseName", "Unknown"),
                                "case_name_short": r.get("caseNameShort"),
                                "court": r.get("court", ""),
                                "court_id": r.get("court_id", ""),
                                "date_filed": r.get("dateFiled"),
                                "date_terminated": r.get("dateTerminated"),
                                "docket_number": r.get("docketNumber"),
                                "nature_of_suit": r.get("suitNature"),
                                "cause": r.get("cause"),
                                "jury_demand": r.get("juryDemand"),
                                "assigned_to": r.get("assignedTo"),
                                "referred_to": r.get("referredTo"),
                                "url": f"https://www.courtlistener.com{r.get('absolute_url', '')}",
                            }
                        )
                        total_pulled += 1
                    except (ValueError, KeyError, TypeError) as e:
                        logger.error(f"Error processing docket {docket_id}: {e}")

                progress_callback(f"Pulled {total_pulled} assigned cases...")

                cursor_url = data.get("next")
                if not cursor_url:
                    break
                # Validate pagination URL stays on courtlistener.com (SSRF prevention)
                from urllib.parse import urlparse as _urlparse

                if _urlparse(cursor_url).hostname not in (
                    "www.courtlistener.com",
                    "courtlistener.com",
                ):
                    logger.warning(f"Pagination URL left courtlistener.com domain: {cursor_url}")
                    break

                await asyncio.sleep(0.1)

        return all_dockets

    async def _pull_citation_data(
        self,
        judge_id: int,
        all_opinions: list[dict],
        progress_callback,
        max_citations: int = 100,
    ) -> list[dict]:
        """
        Pull citation relationship data for the judge's opinions.
        This helps compute citation network and reversal rate estimates.
        """
        opinion_ids = [op["id"] for op in all_opinions if op.get("id")]

        if not opinion_ids:
            return []

        total_pulled = 0
        all_citations = []
        progress_callback(f"Analyzing citation relationships for {len(opinion_ids)} opinions...")

        async with cl_client(timeout=30.0) as client:
            sample_ids = opinion_ids[: min(50, len(opinion_ids))]

            for opinion_id in sample_ids:
                if total_pulled >= max_citations:
                    break

                try:
                    response = await client.get(
                        f"{self.BASE_URL}/opinions-cited/",
                        params={"citing_opinion": opinion_id, "page_size": 20},
                        headers=self.headers,
                        timeout=15.0,
                    )

                    if response.status_code == 200:
                        data = response.json()
                        results = data.get("results", [])

                        for cite in results:
                            cited_id = cite.get("cited_opinion")
                            if isinstance(cited_id, str) and cited_id.startswith("http"):
                                cited_id = cited_id.rstrip("/").split("/")[-1]

                            depth = cite.get("depth", 1)
                            all_citations.append(
                                {
                                    "judge_id": judge_id,
                                    "citing_opinion_id": opinion_id,
                                    "cited_opinion_id": cited_id,
                                    "depth": depth,
                                }
                            )
                            total_pulled += 1

                except (httpx.HTTPError, json.JSONDecodeError, KeyError):  # nosec B110 - Citation data is supplementary
                    pass

                await asyncio.sleep(0.05)

        progress_callback(f"Analyzed {total_pulled} citation relationships")
        return all_citations
