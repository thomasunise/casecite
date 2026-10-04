"""
Obligation extractor — rule-based.

Identifies sentences that express an obligation, using a structured
pipeline rather than free-form LLM analysis:

  1. Sentence-split the contract (offset-aware).
  2. For each sentence:
     - Detect an obligation modal: shall | must | will | agrees to |
       is required to | is obligated to. Permissive "may" (a right, not a
       duty) and hortatory "should" are deliberately NOT obligations.
     - Locate subject (party alias) on the left of the modal
     - Capture the action as a verb phrase: the verb after the modal plus
       up to 8 following words (skipping adverbs like 'not', 'promptly')
     - Capture the rest of the sentence as object_text
     - Extract conditions ("upon", "if", "when", "subject to", "provided that")
     - Categorize via keyword sets
     - Flag mutuality, perpetual, continuing
  3. Dedup on (subject_party, span_start) and on identical matched_text;
     cap the result at 150 obligations in document order.

`link_deadlines(obligations, deadlines)` attaches extracted deadlines to the
obligation whose span contains them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.contract_analysis.parties import ResolvedParty

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")

_MODAL_RE = re.compile(
    r"\b(shall(?:\s+not)?|must(?:\s+not)?|will(?:\s+not)?|agrees?\s+to"
    r"|is\s+required\s+to|is\s+obligated\s+to)\b",
    re.IGNORECASE,
)

_MAX_OBLIGATIONS = 150
_ACTION_MAX_WORDS = 9  # verb + up to 8 words of the predicate
_ACTION_MAX_CHARS = 120

# Bare-bones noise tokens to skip after modal when picking the action verb
_SKIP_AFTER_MODAL = {
    "not",
    "promptly",
    "immediately",
    "timely",
    "reasonably",
    "in",
    "no",
    "event",
    "have",
    "be",
    "the",
    "a",
    "an",
}

_CONDITION_RE = re.compile(
    r"\b(upon|if|when|whenever|subject to|provided that|provided,? however,?|in the event(?: that)?|on the condition that|to the extent (?:that|of))\b",
    re.IGNORECASE,
)

_CATEGORIES: list[tuple[str, list[re.Pattern]]] = [
    (
        "payment",
        [
            re.compile(
                r"\b(pay|invoice|fee|fees|amount|price|reimburs|refund|royalt)", re.IGNORECASE
            ),
        ],
    ),
    (
        "notice",
        [
            re.compile(r"\b(notice|notif|inform|advise)\b", re.IGNORECASE),
        ],
    ),
    (
        "delivery",
        [
            re.compile(r"\b(deliver|provide|furnish|supply|ship|installat)", re.IGNORECASE),
        ],
    ),
    (
        "confidentiality",
        [
            re.compile(r"\b(confidential|disclos(?:e|ure)|protect)\b", re.IGNORECASE),
        ],
    ),
    (
        "ip",
        [
            re.compile(
                r"\b(intellectual property|copyright|patent|trademark|license|assign)",
                re.IGNORECASE,
            ),
        ],
    ),
    (
        "termination",
        [
            re.compile(r"\b(terminat|expir|cancel)", re.IGNORECASE),
        ],
    ),
    (
        "warranty",
        [
            re.compile(r"\b(warrant|represent)", re.IGNORECASE),
        ],
    ),
    (
        "indemnity",
        [
            re.compile(r"\b(indemnif|hold harmless|defend)", re.IGNORECASE),
        ],
    ),
    (
        "compliance",
        [
            re.compile(
                r"\b(complian|complies|comply|laws?|regulations?|FCPA|sanction|export)",
                re.IGNORECASE,
            ),
        ],
    ),
    (
        "reporting",
        [
            re.compile(r"\b(report|certify|certificate|statement|audit)", re.IGNORECASE),
        ],
    ),
]

# Continuing/perpetual flags
_PERPETUAL_RE = re.compile(r"\b(perpetual|in\s+perpetuity|forever)\b", re.IGNORECASE)
_CONTINUING_RE = re.compile(
    r"\b(at\s+all\s+times|continuing|throughout\s+the\s+term)\b", re.IGNORECASE
)


@dataclass
class ExtractedObligation:
    subject_party: str | None
    modal: str
    action: str
    object_text: str
    conditions: list[str] = field(default_factory=list)
    deadlines: list[str] = field(default_factory=list)
    span_start: int = 0
    span_end: int = 0
    matched_text: str = ""
    category: str | None = None
    is_unilateral: bool = False
    is_perpetual: bool = False
    is_continuing: bool = False
    confidence: float = 1.0
    detection_method: str = "rule"


def _categorize(text: str) -> str | None:
    for cat, patterns in _CATEGORIES:
        if any(p.search(text) for p in patterns):
            return cat
    return None


def _split_sentences(text: str) -> list[tuple[str, int, int]]:
    """Sentence split with offsets."""
    out: list[tuple[str, int, int]] = []
    cursor = 0
    pieces = _SENT_SPLIT_RE.split(text)
    for p in pieces:
        if not p:
            continue
        start = text.find(p, cursor)
        if start < 0:
            start = cursor
        end = start + len(p)
        out.append((p, start, end))
        cursor = end
    return out


def _resolve_subject(
    sentence: str, modal_start: int, parties: list[ResolvedParty]
) -> tuple[str | None, str | None]:
    """Look for a known party alias to the left of the modal verb."""
    left = sentence[:modal_start]
    # Search aliases ordered by length descending (longer aliases first)
    candidates: list[tuple[str, str]] = []  # (alias, canonical_name)
    for p in parties:
        for a in p.aliases:
            candidates.append((a, p.canonical_name))
    candidates.sort(key=lambda x: -len(x[0]))
    for alias, canonical in candidates:
        if re.search(r"\b" + re.escape(alias) + r"\b", left, re.IGNORECASE):
            return canonical, alias
    # Generic
    for tok in (
        "Each party",
        "Either party",
        "Neither party",
        "The parties",
        "Both parties",
        "The Company",
        "The Employee",
    ):
        if re.search(r"\b" + re.escape(tok) + r"\b", left, re.IGNORECASE):
            return tok, tok
    return None, None


def _extract_action(sentence: str, modal_match: re.Match) -> tuple[str, str]:
    """Pull the verb phrase following the modal and the rest as object.

    The action is the verb plus up to 8 following words of the predicate
    (bounded by the sentence), kept under 120 chars — a meaningful phrase
    like "pay all invoices within thirty days", not a lone token.
    """
    after = sentence[modal_match.end() :].strip()
    if not after:
        return "(unspecified)", ""
    tokens = after.split()
    # Skip leading fillers
    i = 0
    while i < len(tokens) and tokens[i].rstrip(",.;:").lower() in _SKIP_AFTER_MODAL:
        i += 1
    if i >= len(tokens):
        return "(unspecified)", after
    phrase = " ".join(tokens[i : i + _ACTION_MAX_WORDS]).rstrip(",.;:")
    action = phrase[:_ACTION_MAX_CHARS].rstrip()
    object_text = " ".join(tokens[i + 1 :])
    return action, object_text


def _normalize_modal(raw: str) -> str:
    modal = re.sub(r"\s+", " ", raw.lower())
    return {
        "agrees to": "agrees_to",
        "agree to": "agrees_to",
        "is required to": "is_required_to",
        "is obligated to": "is_obligated_to",
    }.get(modal, modal)


def extract_obligations(
    text: str,
    parties: list[ResolvedParty],
) -> list[ExtractedObligation]:
    if not text:
        return []
    obligations: list[ExtractedObligation] = []
    seen_keys: set[tuple[str | None, int]] = set()
    seen_texts: set[str] = set()

    for sentence, s_start, _ in _split_sentences(text):
        for m in _MODAL_RE.finditer(sentence):
            modal = _normalize_modal(m.group(1))
            subject, _ = _resolve_subject(sentence, m.start(), parties)
            matched_text = sentence[:600]

            # Dedup: same (subject, span_start) or identical text keeps the first.
            key = (subject, s_start)
            if key in seen_keys or matched_text in seen_texts:
                continue
            seen_keys.add(key)
            seen_texts.add(matched_text)

            action, object_text = _extract_action(sentence, m)
            conditions = [c.group(0) for c in _CONDITION_RE.finditer(sentence)]
            cat = _categorize(sentence)
            unilateral = bool(subject) and not re.search(
                r"\b(each|both|either|neither)\b", sentence, re.IGNORECASE
            )
            perpetual = bool(_PERPETUAL_RE.search(sentence))
            continuing = bool(_CONTINUING_RE.search(sentence))
            obligations.append(
                ExtractedObligation(
                    subject_party=subject,
                    modal=modal,
                    action=action,
                    object_text=object_text[:600],
                    conditions=conditions,
                    deadlines=[],  # filled by link_deadlines()
                    span_start=s_start,
                    span_end=s_start + len(sentence),
                    matched_text=matched_text,
                    category=cat,
                    is_unilateral=unilateral,
                    is_perpetual=perpetual,
                    is_continuing=continuing,
                    confidence=0.9 if subject else 0.7,
                )
            )
            if len(obligations) >= _MAX_OBLIGATIONS:
                return obligations
    return obligations


def link_deadlines(obligations: list[ExtractedObligation], deadlines: list) -> None:
    """Attach extracted deadlines to the obligations that contain them.

    A deadline whose span_start falls within [obligation.span_start,
    obligation.span_end] has its description (or matched_text when there is
    no description) appended to that obligation's `deadlines` list. Each
    deadline attaches to at most one obligation — the first that contains it.
    Mutates the obligations in place.
    """
    for d in deadlines:
        d_start = getattr(d, "span_start", None)
        if d_start is None:
            continue
        label = getattr(d, "description", None) or getattr(d, "matched_text", None)
        if not label:
            continue
        for o in obligations:
            if o.span_start <= d_start <= o.span_end:
                o.deadlines.append(label)
                break
