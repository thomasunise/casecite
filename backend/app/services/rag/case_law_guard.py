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
# Horizontal whitespace only: a case name never spans a line break, and
# letting it do so swallowed a heading above "Per Smith v. Jones" into the
# match (and into the redaction).
_GAP = r"[^\S\r\n]+"
_PARTY = rf"{_WORD}(?:{_GAP}(?:{_CONNECTOR}{_GAP})?{_WORD}){{0,5}}"
_CASE_NAME_RE = re.compile(rf"\b({_PARTY}){_GAP}vs?\.?{_GAP}({_PARTY})")

# Single-party captions: "In re Smith", "In the Matter of Smith", "Matter of
# Smith", "Ex parte Young". Matched in their conventional capitalization only
# ("Ex Parte Application" is a document title, "ex parte order" an adjective).
_SINGLE_PARTY_RE = re.compile(
    rf"\b(In{_GAP}[Rr]e|In{_GAP}the{_GAP}Matter{_GAP}of|Matter{_GAP}of|Ex{_GAP}parte)"
    rf"{_GAP}({_PARTY})"
)

# Capitalized words the party regex can pick up from the surrounding sentence
# ("In Smith v. Jones", "See Roe v. Wade") that are not part of the name.
_LEAD_IN_WORDS = {
    "in",
    "see",
    "under",
    "as",
    "per",
    "but",
    "and",
    "also",
    "cf",
    "unlike",
    "like",
    "following",
    "citing",
    "compare",
    "with",
    "accord",
    "contra",
    "although",
    "while",
    "since",
    "because",
    "the",
}


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, unify v./vs./versus."""
    t = re.sub(r"[^\w\s]", " ", text.lower())
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\b(?:vs|versus)\b", "v", t)
    return t


class _Sources:
    """What a case reference in the answer may legitimately be traced to."""

    def __init__(
        self,
        case_law_results: list[dict[str, Any]] | None,
        search_results: list[dict[str, Any]] | None,
    ):
        # Case names of this request's CourtListener results: (left, right)
        # word sets for "A v. B" captions. These are trusted names, so the
        # answer may shorten them ("Smith v. Jones" for "John Smith v. Acme
        # Jones Corp.") as long as every party word it uses belongs to them.
        self.names: list[tuple[set[str], set[str]]] = []
        # Every normalized text a reference may appear in verbatim: the names
        # and citations above, opinion text, and the user's own passages
        # (client filings legitimately quote and discuss cases).
        self.texts: list[str] = []

        for result in case_law_results or []:
            metadata = result.get("metadata") or {}
            for key in ("case_name", "citation", "filename"):
                if metadata.get(key):
                    self._add_text(str(metadata[key]))
            for key in ("case_name", "filename"):
                if metadata.get(key):
                    self._add_name(str(metadata[key]))
            if result.get("text"):
                self._add_text(str(result["text"]))
        for result in search_results or []:
            if result.get("text"):
                self._add_text(str(result["text"]))
            metadata = result.get("metadata") or {}
            if metadata.get("filename"):
                self._add_text(str(metadata["filename"]))

    def _add_text(self, text: str) -> None:
        normalized = _normalize(text)
        if normalized:
            # Padded so " phrase " membership is a whole-word phrase match.
            self.texts.append(f" {normalized} ")

    def _add_name(self, name: str) -> None:
        # Drop a trailing "(123 F.3d 456)" citation from filename-style names.
        left, sep, right = _normalize(name.split("(")[0]).partition(" v ")
        if sep and left and right:
            self.names.append((set(left.split()), set(right.split())))

    def has_phrase(self, phrase: str) -> bool:
        """True when ``phrase`` occurs as whole words in any source text."""
        needle = f" {phrase} "
        return any(needle in text for text in self.texts)

    def allows_case_name(self, party1: str, party2: str) -> bool:
        """Is "party1 v. party2" traceable to a source as a CASE NAME?

        The two party strings each appearing somewhere in the sources is not
        enough — "State" and "Smith" occur in almost any legal text. The
        reference must match a retrieved case's caption party-for-party, or
        appear in a source text as the contiguous phrase "<party1> v <party2>".
        """
        p1 = _normalize(party1).split()
        p2 = _normalize(party2).split()
        # Sentence lead-ins captured ahead of the name are not part of it.
        while len(p1) > 1 and p1[0] in _LEAD_IN_WORDS:
            p1 = p1[1:]
        if not p1 or not p2:
            return False

        for left, right in self.names:
            # Every word of the first party must belong to the caption's first
            # party; the second party must START with one of its words (what
            # follows may be sentence text the pattern swept up: "Jones. The").
            if all(word in left for word in p1) and p2[0] in right:
                return True

        return self.has_phrase(f"{' '.join(p1)} v {p2[0]}")

    def allows_single_party(self, prefix: str, party: str) -> bool:
        """Is an "In re X" / "Matter of X" / "Ex parte X" caption in a source?"""
        words = _normalize(party).split()
        if not words:
            return False
        kind = _normalize(prefix)
        variants = [kind]
        if kind == "in the matter of":
            variants.append("matter of")
        elif kind == "matter of":
            variants.append("in the matter of")
        return any(self.has_phrase(f"{variant} {words[0]}") for variant in variants)


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


def _trim_trailing_punctuation(content: str, start: int, end: int) -> int:
    """Party words may match abbreviation periods; don't let the span swallow
    trailing sentence punctuation ("Roe v. Wade.")."""
    while end > start and content[end - 1] in ".,;:":
        end -= 1
    return end


def find_unverified_case_references(
    content: str,
    case_law_results: list[dict[str, Any]] | None = None,
    search_results: list[dict[str, Any]] | None = None,
) -> list[tuple[int, int]]:
    """Spans of case references in ``content`` not traceable to any source."""
    sources = _Sources(case_law_results, search_results)
    spans: list[tuple[int, int]] = []

    for m in _CASE_NAME_RE.finditer(content):
        if not sources.allows_case_name(m.group(1), m.group(2)):
            spans.append((m.start(), _trim_trailing_punctuation(content, m.start(), m.end())))

    for m in _SINGLE_PARTY_RE.finditer(content):
        if not sources.allows_single_party(m.group(1), m.group(2)):
            spans.append((m.start(), _trim_trailing_punctuation(content, m.start(), m.end())))

    for regex in (_REPORTER_CITE_RE, _WL_CITE_RE):
        for m in regex.finditer(content):
            if not sources.has_phrase(_normalize(m.group(0))):
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
