"""Wikipedia integration mixin for JudgeIntelService."""

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class WikipediaMixin:
    """Wikipedia data fetching for judge biographies."""

    async def fetch_wikipedia_data(
        self, judge_name: str, judge_title: str = "judge"
    ) -> dict[str, Any]:
        """
        Fetch comprehensive biographical data from Wikipedia.

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

                if not search_results:
                    return result

                # Find the best match (prefer titles containing the judge's last name)
                last_name = search_name.split()[-1].lower() if search_name else ""
                page_title = None
                for sr in search_results:
                    title = sr.get("title", "")
                    if last_name in title.lower():
                        page_title = title
                        break

                if not page_title:
                    page_title = search_results[0].get("title")

                if not page_title:
                    return result

                result["url"] = f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"

                # Step 2: Get page summary
                summary_params = {
                    "action": "query",
                    "titles": page_title,
                    "prop": "extracts",
                    "exintro": True,
                    "explaintext": True,
                    "format": "json",
                }

                resp = await client.get(search_url, params=summary_params)
                if resp.status_code == 200:
                    summary_data = resp.json()
                    pages = summary_data.get("query", {}).get("pages", {})
                    for page_id, page_content in pages.items():
                        if page_id != "-1":
                            result["summary"] = page_content.get("extract", "")
                            break

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
