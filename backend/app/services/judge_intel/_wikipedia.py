"""Wikipedia integration mixin for JudgeIntelService."""

import logging
import re
import unicodedata
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_JUDICIAL_RE = re.compile(r"\b(judge|justice|jurist|magistrate|judiciary)\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(1[6-9]\d{2}|20\d{2})\b")
# How many name-matching search hits to inspect before giving up.
_MAX_CANDIDATES = 3


def _name_tokens(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.findall(r"[a-z]+", folded.lower())


def title_matches_judge(title: str, judge_name: str) -> bool:
    """True when a Wikipedia page title names this person.

    The whole last name must appear, and the first name (or its initial) too:
    a shared surname is not a match.
    """
    name = _name_tokens(judge_name)
    if len(name) < 2:
        return False
    # Drop a trailing disambiguator such as "(judge)" before comparing.
    page = _name_tokens(re.sub(r"\s*\([^)]*\)\s*$", "", title))
    first, last = name[0], name[-1]
    if last not in page:
        return False
    return any(
        t == first or (len(t) == 1 and first.startswith(t)) or (len(first) == 1 and t[0] == first)
        for t in page
        if t != last
    )


def intro_describes_judge(intro: str | None, birth_year: int | None = None) -> bool:
    """True when a page's opening describes a judge — and, when the birth year
    is known and the page states one, the same person."""
    if not intro:
        return False
    opening = intro[:1500]
    if not _JUDICIAL_RE.search(opening):
        return False
    if birth_year:
        dates = re.search(r"\(([^)]*)\)", opening[:400])
        years = _YEAR_RE.findall(dates.group(1)) if dates else []
        if years and int(years[0]) != birth_year:
            return False
    return True


class WikipediaMixin:
    """Wikipedia data fetching for judge biographies."""

    async def fetch_wikipedia_data(
        self, judge_name: str, judge_title: str = "judge", birth_year: int | None = None
    ) -> dict[str, Any]:
        """
        Fetch comprehensive biographical data from Wikipedia.

        A page is used only when its title names this person AND its opening
        describes a judge (and matches ``birth_year`` when both are known).
        Anything less returns the empty result: showing no biography is fine,
        showing a namesake's is not.

        Returns dict with:
        - url: Wikipedia page URL
        - summary: Page summary/intro
        - sections: Dict of section name -> content
        - raw: Full page text
        """

        result = {
            "url": None,
            "summary": None,
            "bio": None,
            "early_life": None,
            "education": None,
            "career": None,
            "judicial_service": None,
            "notable_cases": None,
            "personal_life": None,
            "raw": None,
        }

        # Clean up the name for searching
        search_name = judge_name.strip()

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Search Wikipedia for the judge
            search_url = "https://en.wikipedia.org/w/api.php"
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": f"{search_name} {judge_title}",
                "srlimit": 5,
                "format": "json",
            }

            try:
                resp = await client.get(search_url, params=search_params)
                if resp.status_code != 200:
                    return result

                search_data = resp.json()
                search_results = search_data.get("query", {}).get("search", [])

                if not search_results:
                    # Try without "judge" suffix
                    search_params["srsearch"] = search_name
                    resp = await client.get(search_url, params=search_params)
                    search_data = resp.json()
                    search_results = search_data.get("query", {}).get("search", [])

                # Step 2: Among the hits whose title names this person, take the
                # first whose opening actually describes a judge.
                candidates = [
                    sr.get("title", "")
                    for sr in search_results
                    if title_matches_judge(sr.get("title", ""), search_name)
                ][:_MAX_CANDIDATES]
                page_title = None
                for title in candidates:
                    summary_params = {
                        "action": "query",
                        "titles": title,
                        "prop": "extracts",
                        "exintro": True,
                        "explaintext": True,
                        "format": "json",
                    }
                    resp = await client.get(search_url, params=summary_params)
                    if resp.status_code != 200:
                        continue
                    pages = resp.json().get("query", {}).get("pages", {})
                    intro = next(
                        (pc.get("extract", "") for pid, pc in pages.items() if pid != "-1"), ""
                    )
                    if intro_describes_judge(intro, birth_year):
                        page_title = title
                        result["summary"] = intro
                        break

                if not page_title:
                    logger.info(f"No confirmed Wikipedia page for judge {judge_name}")
                    return result

                result["url"] = f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"

                # Step 3: Get full page content with sections
                content_params = {
                    "action": "query",
                    "titles": page_title,
                    "prop": "extracts",
                    "explaintext": True,
                    "format": "json",
                }

                resp = await client.get(search_url, params=content_params)
                if resp.status_code == 200:
                    content_data = resp.json()
                    pages = content_data.get("query", {}).get("pages", {})
                    for page_id, page_content in pages.items():
                        if page_id != "-1":
                            full_text = page_content.get("extract", "")
                            result["raw"] = full_text
                            result["bio"] = full_text[:5000] if full_text else None

                            # Parse sections from the full text
                            sections = self._parse_wikipedia_sections(full_text)
                            result["early_life"] = sections.get("early_life")
                            result["education"] = sections.get("education")
                            result["career"] = sections.get("career")
                            result["judicial_service"] = sections.get("judicial_service")
                            result["notable_cases"] = sections.get("notable_cases")
                            result["personal_life"] = sections.get("personal_life")
                            break

            except (
                httpx.HTTPError,
                ValueError,
                KeyError,
                ConnectionError,
                TimeoutError,
                OSError,
                RuntimeError,
            ) as e:
                logger.error(f"Wikipedia fetch error for {judge_name}: {e}")

        return result

    def _parse_wikipedia_sections(self, text: str) -> dict[str, str]:
        """Parse Wikipedia article text into sections."""
        sections = {}

        # Common section patterns in judicial biographies
        section_patterns = {
            "early_life": r"(?:early life|early years|childhood|biography|background)",
            "education": r"(?:education|academic|school|university|college)",
            "career": r"(?:career|legal career|professional|practice|work)",
            "judicial_service": r"(?:judicial|judge|court|bench|nomination|confirmation|service)",
            "notable_cases": r"(?:notable|significant|important|landmark|cases|decisions|rulings|opinions)",
            "personal_life": r"(?:personal life|family|marriage|spouse|children|private)",
        }

        # Split by lines that look like section headers (== Header ==)
        lines = text.split("\n")
        current_section = "intro"
        section_content: dict[str, list[str]] = {current_section: []}

        for line in lines:
            header_match = re.match(r"^={2,}\s*(.+?)\s*={2,}$", line.strip())
            if header_match:
                current_section = header_match.group(1).lower().strip()
                section_content[current_section] = []
            else:
                if current_section not in section_content:
                    section_content[current_section] = []
                section_content[current_section].append(line)

        # Match sections to our categories
        for key, pattern in section_patterns.items():
            for section_name, content in section_content.items():
                if re.search(pattern, section_name, re.IGNORECASE):
                    sections[key] = "\n".join(content).strip()
                    break

        # If no structured sections found, try to extract from full text
        if not sections and text:
            text_lower = text.lower()
            for key, pattern in section_patterns.items():
                match = re.search(pattern, text_lower)
                if match:
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 2000)
                    sections[key] = text[start:end].strip()

        return sections
