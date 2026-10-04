"""
Defined-terms checker.

A defined term is identified by one of the following patterns:
  '"Term" means ...'
  '"Term" shall mean ...'
  '"Term" refers to ...'
  '<X> ("Term") ...'
  ' (the "Term") ...'

For each defined term:
  - count usage occurrences (case-insensitive whole-word match)
  - flag defined_but_unused if usage_count == 1 (only the definition itself)
  - flag circular_reference if the definition body contains the term itself
  - flag used_but_undefined for any capitalized 2-3-word phrase used 3+ times
    that wasn't defined

This helps catch the most common drafting bugs without requiring an LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DEFINED_RE = re.compile(
    r"(?:"
    r'"(?P<a>[A-Z][A-Za-z0-9 \-/]{1,80})"\s+(?:means|shall\s+mean|refers\s+to|is\s+defined\s+as)\s+(?P<def_a>[^.]{5,500}\.)'
    r"|"
    r'\(\s*(?:the\s+)?"(?P<b>[A-Z][A-Za-z0-9 \-/]{1,80})"\s*\)'
    r")"
)

_LIKELY_DEFINED_USE_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b")


@dataclass
class DefinedTermFinding:
    term: str
    definition_text: str | None
    defined: bool
    usage_count: int
    used_but_undefined: bool = False
    defined_but_unused: bool = False
    circular_reference: bool = False
    span_start: int | None = None
    span_end: int | None = None


_STOPWORDS = {
    "Agreement",
    "Section",
    "Article",
    "Schedule",
    "Exhibit",
    "Appendix",
    "Annex",
    "Effective Date",
    "Party",
    "Parties",
    "Recipient",
    "Discloser",
    "Provider",
    "Customer",
    "Licensor",
    "Licensee",
    "Company",
    "Employee",
    "Confidential Information",
    "Terms",
    "Term",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
}


def check_defined_terms(text: str) -> list[DefinedTermFinding]:
    if not text:
        return []
    defined: dict[str, DefinedTermFinding] = {}

    for m in _DEFINED_RE.finditer(text):
        term = (m.group("a") or m.group("b") or "").strip()
        if not term:
            continue
        body = (m.group("def_a") or "").strip() or None
        circular = bool(body and re.search(r"\b" + re.escape(term) + r"\b", body, re.IGNORECASE))
        if term not in defined:
            defined[term] = DefinedTermFinding(
                term=term,
                definition_text=body,
                defined=True,
                usage_count=0,
                circular_reference=circular,
                span_start=m.start(),
                span_end=m.end(),
            )

    # Count usages of each defined term
    for term, finding in defined.items():
        rx = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
        finding.usage_count = len(rx.findall(text))
        if finding.usage_count <= 1:
            finding.defined_but_unused = True

    # Detect used-but-undefined: capitalized 2-3-word phrases used 3+ times
    candidate_counts: dict[str, int] = {}
    for m in _LIKELY_DEFINED_USE_RE.finditer(text):
        w = m.group(1)
        candidate_counts[w] = candidate_counts.get(w, 0) + 1

    for word, count in candidate_counts.items():
        if count < 3:
            continue
        if word in _STOPWORDS:
            continue
        if word in defined:
            continue
        # Single-word candidates are noisy unless quite long
        if " " not in word and len(word) < 6:
            continue
        defined[word] = DefinedTermFinding(
            term=word,
            definition_text=None,
            defined=False,
            usage_count=count,
            used_but_undefined=True,
        )

    return list(defined.values())
