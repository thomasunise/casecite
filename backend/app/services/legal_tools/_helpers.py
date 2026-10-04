"""
Legal Tools - Helper methods, constants, and shared state.
"""

import html as html_lib
import re
from typing import Any

from app.services.courtlistener_client import CourtListenerClientBase

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# CourtListener opinion ``type`` codes → reader-facing labels.
OPINION_TYPE_LABELS = {
    "010combined": "Opinion",
    "015unamimous": "Unanimous opinion",
    "020lead": "Lead opinion",
    "025plurality": "Plurality opinion",
    "030concurrence": "Concurrence",
    "035concurrenceinpart": "Concurrence in part",
    "040dissent": "Dissent",
    "050addendum": "Addendum",
    "060remittitur": "Remittitur",
    "070rehearing": "Rehearing",
    "080onthemerits": "On the merits",
    "090onmotiontostrike": "On motion to strike",
}

# Reporter preference when a case carries several parallel citations: the
# official reporter first, then the widely used unofficial ones.
_REPORTER_RANK = [
    (re.compile(r"\bU\.S\.\s+\d"), 0),
    (re.compile(r"\bF\.\s?(?:2d|3d|4th)\s+\d"), 1),
    (re.compile(r"\bF\.\s+\d"), 2),
    (re.compile(r"\bS\.\s?Ct\.\s+\d"), 3),
    (re.compile(r"\bF\.\s?Supp\.\s?(?:2d|3d)?\s+\d"), 4),
    (re.compile(r"\bB\.R\.\s+\d"), 5),
    (re.compile(r"\bL\.\s?Ed\.\s?(?:2d)?\s+\d"), 8),
    (re.compile(r"\bF\.\s?App'?x\.?\s+\d"), 9),
    (re.compile(r"\b(?:WL|LEXIS|U\.S\.L\.W\.)\b"), 10),
]


def strip_marks(text: str | None) -> str:
    """Drop search-highlight tags (and any other markup) and tidy whitespace."""
    if not text:
        return ""
    text = _TAG_RE.sub("", text)
    text = html_lib.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def nested_snippet(result: dict[str, Any]) -> str:
    """v4 search nests the highlighted snippet under ``opinions[0].snippet``."""
    opinions = result.get("opinions") or []
    if opinions and isinstance(opinions[0], dict):
        return strip_marks(opinions[0].get("snippet"))
    return strip_marks(result.get("snippet"))


def first_opinion_id(result: dict[str, Any]) -> int | None:
    opinions = result.get("opinions") or []
    if opinions and isinstance(opinions[0], dict):
        return opinions[0].get("id")
    return None


def _citation_rank(cite: str) -> int:
    # Vendor-neutral / service cites go last no matter what else they contain.
    if _REPORTER_RANK[-1][0].search(cite):
        return _REPORTER_RANK[-1][1]
    for pattern, rank in _REPORTER_RANK[:-1]:
        if pattern.search(cite):
            return rank
    return 6


def order_citations(citations: list[Any]) -> list[str]:
    """Parallel citations with the official reporter first (stable otherwise)."""
    strings = [str(c).strip() for c in citations if c and str(c).strip()]
    return sorted(strings, key=_citation_rank)


def citation_dict_to_string(c: Any) -> str | None:
    """Cluster endpoints return citations as {volume, reporter, page} dicts."""
    if isinstance(c, str):
        return c.strip() or None
    if isinstance(c, dict):
        parts = [
            str(c.get("volume") or "").strip(),
            str(c.get("reporter") or "").strip(),
            str(c.get("page") or "").strip(),
        ]
        s = " ".join(p for p in parts if p)
        return s or None
    return None


def url_from_relative(rel: str | None) -> str | None:
    if not rel:
        return None
    return rel if rel.startswith("http") else f"https://www.courtlistener.com{rel}"


def trailing_id(url: str | None) -> int | None:
    """``.../api/rest/v4/clusters/12345/`` → 12345."""
    if not url:
        return None
    m = re.search(r"/(\d+)/?$", str(url))
    return int(m.group(1)) if m else None


class HelpersMixin(CourtListenerClientBase):
    """Mixin providing helper methods and shared attributes for legal tools.

    Token handling, date parsing and the jurisdiction map come from the shared
    CourtListener client base.
    """

    # court_id → full court name; courts never change, so process-lifetime cache.
    _court_names: dict[str, str] = {}

    async def _court_name(self, client: Any, court_id: str | None) -> str | None:
        """Resolve a court id (``scotus``, ``cafc``) to its full name, cached."""
        if not court_id:
            return None
        cached = HelpersMixin._court_names.get(court_id)
        if cached:
            return cached
        try:
            resp = await client.get(f"{self.BASE_URL}/courts/{court_id}/", headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                name = data.get("full_name") or data.get("short_name")
                if name:
                    HelpersMixin._court_names[court_id] = name
                    return name
        except Exception:  # a missing court name never fails the tool
            pass
        return None
