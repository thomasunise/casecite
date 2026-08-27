"""
Date / deadline extractor.

Pulls structured deadline records from a contract. Each record carries:
  kind:        absolute | relative_offset | period | recurring
  description: free text as it appeared
  anchor:      effective_date | invoice_date | termination | notice | other
  offset_days: int (positive = after, negative = before)
  period_days: int (for durations / recurring)
  resolved_date: optional concrete datetime when an effective_date is supplied

The output dovetails with the existing CaseCite `discovery_intelligence` deadline
calculator, which already understands jurisdictional holidays — we only
extract the structured offsets here; downstream code can resolve to a
business day if/when needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_NUMBER_WORD: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "ninety-six": 96,
}


def _word_to_int(s: str) -> int | None:
    s = s.lower().strip()
    if s.isdigit():
        return int(s)
    return _NUMBER_WORD.get(s)


_OFFSET_RE = re.compile(
    r"(?P<adv>within|no\s+later\s+than|not\s+later\s+than|on\s+or\s+before|at\s+least|no\s+more\s+than)?\s*"
    r"(?P<num>\d{1,4}|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"twelve|fifteen|eighteen|twenty(?:-?[a-z]+)?|thirty(?:-?[a-z]+)?|sixty|ninety)\s*"
    r"\(?\s*(?:\d+)?\s*\)?\s*"
    r"(?P<unit>days?|business\s+days?|calendar\s+days?|months?|years?|weeks?)"
    r"(?P<rel>\s+(?:after|prior\s+to|before|preceding|following))?",
    re.IGNORECASE,
)

_ABSOLUTE_DATE_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
    r"\d{1,2},\s+\d{4}\b"
)

_PERIOD_RE = re.compile(
    r"\b(?:for\s+a\s+(?:period\s+of\s+)?|during\s+the\s+|term\s+of\s+|of\s+)?"
    r"(?P<num>\d{1,4}|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"twelve|fifteen|eighteen|twenty(?:-?[a-z]+)?|thirty(?:-?[a-z]+)?)\s*"
    r"\(?\s*(?:\d+)?\s*\)?\s*"
    r"(?P<unit>days?|months?|years?)\s+(?:term|period|following|after|thereafter|after the)",
    re.IGNORECASE,
)


def _unit_to_days(unit: str, n: int) -> int:
    u = unit.lower().strip()
    if "day" in u:
        return n
    if "week" in u:
        return n * 7
    if "month" in u:
        return n * 30  # calendar approximation
    if "year" in u:
        return n * 365
    return n


@dataclass
class ExtractedDeadline:
    kind: str
    description: str
    anchor: str | None = None
    offset_days: int | None = None
    period_days: int | None = None
    resolved_date: datetime | None = None
    span_start: int | None = None
    span_end: int | None = None
    matched_text: str | None = None


def _detect_anchor(left_context: str, right_context: str) -> str | None:
    blob = (left_context + " " + right_context).lower()
    if "effective date" in blob:
        return "effective_date"
    if "invoice" in blob:
        return "invoice_date"
    if "termination" in blob or "expir" in blob:
        return "termination"
    if "notice" in blob:
        return "notice"
    if "execution" in blob or "signing" in blob:
        return "execution_date"
    if "delivery" in blob:
        return "delivery"
    return None


def extract_deadlines(text: str, effective_date: datetime | None = None) -> list[ExtractedDeadline]:
    if not text:
        return []
    out: list[ExtractedDeadline] = []

    # 1) Relative offsets: "within 30 days after the Effective Date"
    for m in _OFFSET_RE.finditer(text):
        n = _word_to_int(m.group("num").replace("-", " ").split()[0])
        if n is None:
            # Try to match the full word like "twenty-four"
            n = _word_to_int(m.group("num"))
            if n is None:
                continue
        unit = m.group("unit")
        days = _unit_to_days(unit, n)
        rel = (m.group("rel") or "").lower()
        if "before" in rel or "prior" in rel or "preceding" in rel:
            days = -days
        left_ctx = text[max(0, m.start() - 60) : m.start()]
        right_ctx = text[m.end() : m.end() + 80]
        anchor = _detect_anchor(left_ctx, right_ctx)
        resolved = None
        if effective_date and anchor == "effective_date":
            resolved = effective_date + timedelta(days=days)
        out.append(
            ExtractedDeadline(
                kind="relative_offset",
                description=text[m.start() : m.end()],
                anchor=anchor,
                offset_days=days,
                resolved_date=resolved,
                span_start=m.start(),
                span_end=m.end(),
                matched_text=text[max(0, m.start() - 30) : min(len(text), m.end() + 60)],
            )
        )

    # 2) Periods (durations): "for a period of three (3) years"
    for m in _PERIOD_RE.finditer(text):
        n = _word_to_int(m.group("num").split("-")[0]) or _word_to_int(m.group("num"))
        if n is None:
            continue
        days = _unit_to_days(m.group("unit"), n)
        out.append(
            ExtractedDeadline(
                kind="period",
                description=text[m.start() : m.end()],
                period_days=days,
                span_start=m.start(),
                span_end=m.end(),
                matched_text=text[m.start() : m.end()],
            )
        )

    # 3) Absolute dates
    for m in _ABSOLUTE_DATE_RE.finditer(text):
        try:
            dt = datetime.strptime(m.group(0), "%B %d, %Y")
        except ValueError:
            try:
                dt = datetime.strptime(m.group(0), "%b %d, %Y")
            except ValueError:
                dt = None
        out.append(
            ExtractedDeadline(
                kind="absolute",
                description=m.group(0),
                resolved_date=dt,
                span_start=m.start(),
                span_end=m.end(),
                matched_text=m.group(0),
            )
        )

    return out
