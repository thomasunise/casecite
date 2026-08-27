"""Case-law citation guard — pipeline enforcement, not prompt trust.

Product rule: the model is NEVER trusted for case law. Every case reference in
a chat answer must be traceable to a CourtListener result retrieved for this
request, or appear in the user's own retrieved document passages (client
filings legitimately quote and discuss cases — repeating what they say is
grounded). Any case name or reporter citation the model produced from its own
weights is redacted before the response leaves the backend.

The system prompt already tells the model not to invent authority; this module
is the mechanism that makes the rule hold regardless of what the model does.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

REDACTION = "[unverified case-law reference removed]"


# Two-letter regional reporters ("N.E.", "S.W.") are ambiguous without their
# periods (street addresses: "123 NE 45"), so the bare form additionally
# requires a series suffix. Everything else matches loosely on punctuation and
# spacing — hallucinated citations don't follow Bluebook any better than real
# ones.
def _regional(a: str, b: str) -> str:
    return rf"(?:{a}\.\s?{b}\.(?:\s?(?:2d|3d))?|{a}\.?\s?{b}\.?\s?(?:2d|3d))"


_REPORTERS = [
    r"U\.?\s?S\.?",
    r"S\.?\s?Ct\.?",
    r"L\.?\s?Ed\.?(?:\s?2d)?",
    r"F\.?\s?(?:2d|3d|4th)",
    r"F\.?\s?Supp\.?(?:\s?(?:2d|3d))?",
    r"F\.?\s?App'?x\.?",
    r"B\.?\s?R\.?",
    r"P\.?\s?(?:2d|3d)",
    _regional("N", "E"),
    _regional("N", "W"),
    _regional("S", "E"),
    _regional("S", "W"),
    r"A\.?\s?(?:2d|3d)",
    r"So\.?\s?(?:2d|3d)",
    r"Cal\.?\s?Rptr\.?(?:\s?(?:2d|3d))?",
    r"N\.?\s?Y\.?\s?S\.?(?:\s?(?:2d|3d))?",
]

_REPORTER_CITE_RE = re.compile(r"\b\d{1,4}\s+(?:" + "|".join(_REPORTERS) + r")\s+\d{1,5}\b")
_WL_CITE_RE = re.compile(r"\b(?:19|20)\d{2}\s+WL\s+\d{1,9}\b")

# "Smith v. Jones" style names: capitalized parties either side of v./vs.,
# with lowercase connectors ("Board of Education") only between capitalized
# words so the match never trails off into ordinary prose.
_CONNECTOR = r"(?:of|the|and|for|in|de|del|la|van|von|ex|rel\.?)"
_WORD = r"[A-Z][A-Za-z'’&.-]*"
_PARTY = rf"{_WORD}(?:\s+(?:{_CONNECTOR}\s+)?{_WORD}){{0,5}}"
_CASE_NAME_RE = re.compile(rf"\b({_PARTY})\s+vs?\.?\s+({_PARTY})")


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, unify v./vs./versus."""
    t = re.sub(r"[^\w\s]", " ", text.lower())
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\b(?:vs|versus)\b", "v", t)
    return t


def _allowed_parts(
    case_law_results: list[dict[str, Any]] | None,
    search_results: list[dict[str, Any]] | None,
) -> list[str]:
    """Normalized texts a case reference may legitimately come from."""
    parts: list[str] = []
    for result in case_law_results or []:
        metadata = result.get("metadata") or {}
        for key in ("case_name", "citation", "filename"):
            if metadata.get(key):
                parts.append(str(metadata[key]))
        if result.get("text"):
            parts.append(str(result["text"]))
    for result in search_results or []:
        if result.get("text"):
            parts.append(str(result["text"]))
        metadata = result.get("metadata") or {}
        if metadata.get("filename"):
            parts.append(str(metadata["filename"]))
    return [_normalize(p) for p in parts if p]


def _merge_spans(spans: list[tuple[int, int]], content: str) -> list[tuple[int, int]]:
    """Merge overlapping/adjacent spans ("Name v. Other, 123 F.3d 456")."""
    if not spans:
        return []
    spans.sort()
    merged = [spans[0]]
    for start, end in spans[1:]:
        prev_start, prev_end = merged[-1]
        gap = content[prev_end:start]
        if start <= prev_end or (len(gap) <= 3 and not gap.strip(" ,;:(")):
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def find_unverified_case_references(
    content: str,
    case_law_results: list[dict[str, Any]] | None = None,
    search_results: list[dict[str, Any]] | None = None,
) -> list[tuple[int, int]]:
    """Spans of case references in ``content`` not traceable to any source."""
    parts = _allowed_parts(case_law_results, search_results)
    spans: list[tuple[int, int]] = []

    for m in _CASE_NAME_RE.finditer(content):
        p1, p2 = _normalize(m.group(1)), _normalize(m.group(2))
        if not any(p1 in part and p2 in part for part in parts):
            # Party words may match abbreviation periods; don't let the span
            # swallow trailing sentence punctuation ("Roe v. Wade.").
            end = m.end()
            while end > m.start() and content[end - 1] in ".,;:":
                end -= 1
            spans.append((m.start(), end))

    for regex in (_REPORTER_CITE_RE, _WL_CITE_RE):
        for m in regex.finditer(content):
            if not any(_normalize(m.group(0)) in part for part in parts):
                spans.append((m.start(), m.end()))

    return _merge_spans(spans, content)


def redact_unverified_case_law(
    content: str,
    case_law_results: list[dict[str, Any]] | None = None,
    search_results: list[dict[str, Any]] | None = None,
) -> tuple[str, list[str]]:
    """Redact every unverifiable case reference in ``content``.

    Returns (clean_content, removed_reference_texts). When anything was
    removed, a visible note is appended so the reader knows the answer was
    policed rather than silently altered.
    """
    if not content:
        return content, []
    spans = find_unverified_case_references(content, case_law_results, search_results)
    if not spans:
        return content, []

    removed = [content[start:end] for start, end in spans]
    for start, end in reversed(spans):
        content = content[:start] + REDACTION + content[end:]

    n = len(removed)
    content += (
        f"\n\n> ⚠ {n} case-law reference{'s' if n != 1 else ''} "
        f"{'were' if n != 1 else 'was'} removed because "
        f"{'they' if n != 1 else 'it'} could not be verified against this "
        "request's CourtListener results. Case law here is only cited from "
        "real CourtListener authorities — run Case Citations on a filing for "
        "quote-verified support."
    )
    return content, removed
