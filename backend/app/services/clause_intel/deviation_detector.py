"""
Deviation detector.

For each tagged clause, compare against the canonical market-standard
reference and flag substantive deviations. The detector is *rule-based*
on top of structured sub-element detection — the LLM does not decide
whether something is a deviation.

Categories:
  missing_subelement       — required sub-element absent in the matched clause
  weakened                 — protective sub-element present in canonical, missing here
  strengthened             — extra protective sub-element compared to canonical
  reversed                 — directional flip (e.g., mutual ↔ unilateral)
  scope_change             — geographic / field / duration scope materially different
  cap_change               — liability cap removed or materially altered
  mutual_to_unilateral     — mutuality removed
  unilateral_to_mutual     — mutuality added
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Deviation:
    canonical_slug: str
    canonical_id: int | None
    deviation_type: str
    sub_element: str | None
    severity: str  # critical | major | minor | informational
    matched_text: str
    span_start: int | None
    span_end: int | None
    classifier_confidence: float | None
    detail: dict


# Severity policy — drives prioritization of deviations.
_SEVERITY_BY_SUBELEMENT: dict[tuple[str, str], str] = {
    ("limitation_of_liability", "aggregate_cap"): "critical",
    ("limitation_of_liability", "consequential_exclusion"): "major",
    ("limitation_of_liability", "carveouts"): "major",
    ("indemnification", "scope"): "critical",
    ("indemnification", "procedure"): "major",
    ("warranty_disclaimer", "as_is"): "major",
    ("warranty_disclaimer", "implied_disclaimed"): "major",
    ("ip_assignment", "present_assignment"): "critical",
    ("confidentiality", "definition"): "major",
    ("confidentiality", "exclusions"): "major",
    ("confidentiality", "term_of_protection"): "major",
    ("data_security", "incident_notification"): "critical",
    ("data_security", "encryption"): "major",
    ("termination_for_cause", "cure_period"): "major",
    ("termination_for_cause", "material_breach"): "major",
    ("non_compete", "duration"): "major",
    ("non_compete", "geography"): "major",
    ("non_compete", "scope_of_activity"): "major",
    ("jury_waiver", "conspicuous"): "major",
    ("payment_terms", "due_period"): "major",
    ("payment_terms", "taxes"): "major",
    ("governing_law", "jurisdiction_named"): "critical",
    ("venue_jurisdiction", "specific_courts"): "major",
    ("arbitration", "rules_administrator"): "major",
    ("arbitration", "seat"): "major",
    ("entire_agreement", "integration"): "major",
}


def _severity(canonical_slug: str, sub_key: str, required: bool) -> str:
    explicit = _SEVERITY_BY_SUBELEMENT.get((canonical_slug, sub_key))
    if explicit:
        return explicit
    if required:
        return "major"
    return "minor"


# Detection helpers -----------------------------------------------------------


_MUTUAL_RE = re.compile(r"(?i)\b(?:each|either|both)\s+part(?:y|ies)|mutual")
_ONE_PARTY_RE = re.compile(
    r"(?i)\b(?:provider|customer|licensee|licensor|company|recipient|employee)\s+(?:shall|will|agrees)"
)


def _mutuality(text: str) -> str | None:
    """Return 'mutual' | 'unilateral' | None (insufficient signal)."""
    has_mutual = bool(_MUTUAL_RE.search(text))
    one_party_hits = len(_ONE_PARTY_RE.findall(text))
    if has_mutual:
        return "mutual"
    if one_party_hits >= 1 and not has_mutual:
        return "unilateral"
    return None


_DURATION_RE = re.compile(
    r"(?i)\b(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|eighteen|twenty[\s-]?four|thirty[\s-]?six)\s+(?:\(\d+\)\s+)?(month|months|year|years)\b"
)
_NUMBER_WORD = {
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
    "twelve": 12,
    "fifteen": 15,
    "eighteen": 18,
    "twenty-four": 24,
    "twenty four": 24,
    "thirty-six": 36,
    "thirty six": 36,
}


def _extract_max_duration_months(text: str) -> int | None:
    found_months: list[int] = []
    for m in _DURATION_RE.finditer(text):
        raw_num = m.group(1).lower().strip()
        unit = m.group(2).lower()
        if raw_num.isdigit():
            n = int(raw_num)
        else:
            n = _NUMBER_WORD.get(raw_num)
            if n is None:
                continue
        if unit.startswith("year"):
            n *= 12
        found_months.append(n)
    return max(found_months) if found_months else None


_DOLLAR_CAP_RE = re.compile(r"\$\s?[\d,]+(?:\.\d+)?(?:\s*(?:million|thousand|M|K))?")
_FEES_PAID_CAP_RE = re.compile(
    r"(?i)(?:fees\s+paid|amounts?\s+paid|amounts?\s+payable).{0,80}(?:in\s+the\s+(?:twelve|six)\s*\(?\d*\)?\s*months?|preceding|prior)"
)


def _has_cap_floor(text: str) -> bool:
    return bool(_DOLLAR_CAP_RE.search(text)) or bool(_FEES_PAID_CAP_RE.search(text))


# =============================================================================
# Public detector
# =============================================================================


def detect_deviations(
    canonical: dict,
    matched_text: str,
    detected_sub_elements: list[str],
    span_start: int | None = None,
    span_end: int | None = None,
    classifier_confidence: float | None = None,
) -> list[Deviation]:
    """
    Compare a tagged clause against its canonical and emit structured deviations.
    """
    deviations: list[Deviation] = []
    detected = set(detected_sub_elements)
    canonical_slug = canonical["slug"]

    # 1) Missing sub-elements
    for sub in canonical.get("sub_elements") or []:
        if sub["key"] not in detected:
            sev = _severity(canonical_slug, sub["key"], required=bool(sub.get("required")))
            deviations.append(
                Deviation(
                    canonical_slug=canonical_slug,
                    canonical_id=canonical.get("id"),
                    deviation_type="missing_subelement" if sub.get("required") else "weakened",
                    sub_element=sub["key"],
                    severity=sev if sub.get("required") else "minor",
                    matched_text=matched_text[:600],
                    span_start=span_start,
                    span_end=span_end,
                    classifier_confidence=classifier_confidence,
                    detail={
                        "missing": sub["key"],
                        "name": sub["name"],
                        "description": sub["description"],
                        "required": bool(sub.get("required")),
                    },
                )
            )

    # 2) Mutuality flip
    if any(s["key"] == "mutual" for s in canonical.get("sub_elements") or []):
        canonical_mut = _mutuality(canonical.get("market_standard_text") or "")
        actual_mut = _mutuality(matched_text)
        if canonical_mut and actual_mut and canonical_mut != actual_mut:
            deviation_type = (
                "mutual_to_unilateral"
                if canonical_mut == "mutual" and actual_mut == "unilateral"
                else "unilateral_to_mutual"
            )
            deviations.append(
                Deviation(
                    canonical_slug=canonical_slug,
                    canonical_id=canonical.get("id"),
                    deviation_type=deviation_type,
                    sub_element="mutual",
                    severity="major",
                    matched_text=matched_text[:600],
                    span_start=span_start,
                    span_end=span_end,
                    classifier_confidence=classifier_confidence,
                    detail={
                        "canonical_mutuality": canonical_mut,
                        "observed_mutuality": actual_mut,
                    },
                )
            )

    # 3) Liability cap removal / material change
    if canonical_slug == "limitation_of_liability":
        if not _has_cap_floor(matched_text):
            deviations.append(
                Deviation(
                    canonical_slug=canonical_slug,
                    canonical_id=canonical.get("id"),
                    deviation_type="cap_change",
                    sub_element="aggregate_cap",
                    severity="critical",
                    matched_text=matched_text[:600],
                    span_start=span_start,
                    span_end=span_end,
                    classifier_confidence=classifier_confidence,
                    detail={"observation": "no numeric or fees-paid cap detected"},
                )
            )

    # 4) Non-compete duration scope
    if canonical_slug == "non_compete":
        max_months = _extract_max_duration_months(matched_text)
        if max_months is None:
            deviations.append(
                Deviation(
                    canonical_slug=canonical_slug,
                    canonical_id=canonical.get("id"),
                    deviation_type="scope_change",
                    sub_element="duration",
                    severity="major",
                    matched_text=matched_text[:600],
                    span_start=span_start,
                    span_end=span_end,
                    classifier_confidence=classifier_confidence,
                    detail={"observation": "no duration detected — likely overbroad"},
                )
            )
        elif max_months > 24:
            deviations.append(
                Deviation(
                    canonical_slug=canonical_slug,
                    canonical_id=canonical.get("id"),
                    deviation_type="scope_change",
                    sub_element="duration",
                    severity="major",
                    matched_text=matched_text[:600],
                    span_start=span_start,
                    span_end=span_end,
                    classifier_confidence=classifier_confidence,
                    detail={
                        "observed_months": max_months,
                        "common_outer_limit_months": 24,
                    },
                )
            )

    # 5) Cure-period absence on termination-for-cause
    if canonical_slug == "termination_for_cause" and "cure_period" not in detected:
        deviations.append(
            Deviation(
                canonical_slug=canonical_slug,
                canonical_id=canonical.get("id"),
                deviation_type="missing_subelement",
                sub_element="cure_period",
                severity="major",
                matched_text=matched_text[:600],
                span_start=span_start,
                span_end=span_end,
                classifier_confidence=classifier_confidence,
                detail={
                    "observation": "cure period not stated — termination may be too aggressive"
                },
            )
        )

    return deviations
