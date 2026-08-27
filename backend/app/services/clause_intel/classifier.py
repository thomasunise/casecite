"""
Clause classifier — embedding + regex hybrid.

Pipeline:
  1. Segment the document into clause-sized chunks (heading-aware, then paragraph fallback).
  2. For each chunk:
     a. Run regex anchors against every canonical type. Any anchor hit → high-confidence tag candidate.
     b. Compute embedding similarity to every canonical's reference embedding.
     c. Combine: hybrid score = max(regex_hit ? 0.95 : 0, alpha * embedding_sim + beta * keyword_overlap)
     d. Tag chunks above threshold.
  3. For each tagged chunk, run sub-element detection (regex + keyword) against canonical sub_elements.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clause_intel import ClauseCanonical
from app.services.clause_intel.taxonomy_seed import CANONICAL_CLAUSES

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

EMBED_THRESHOLD = 0.55
HYBRID_THRESHOLD = 0.50
REGEX_CONFIDENCE = 0.95


@dataclass
class Segment:
    text: str
    start: int
    end: int


@dataclass
class TagCandidate:
    canonical_slug: str
    canonical_id: int | None
    segment: Segment
    method: str  # regex | embedding | hybrid
    confidence: float
    detected_sub_elements: list[str]


# =============================================================================
# Document segmentation
# =============================================================================

_HEADING_RE = re.compile(
    r"""(?xm)
    ^
    (?:
        \s*\d+(?:\.\d+)*\s*\.?\s+[A-Z][A-Za-z0-9 ,\-/&'()]+\s*$        # 1. Heading  /  1.2 Heading
      | \s*ARTICLE\s+[IVXLCDM\d]+[\.\s].*$                              # ARTICLE V
      | \s*SECTION\s+\d+(?:\.\d+)*\s*\.?\s*.*$                          # SECTION 4.2
      | \s*[A-Z][A-Z &/\-]{3,40}\s*$                                    # ALL CAPS HEADING
      | \s*\(?[a-z]\)\s+[A-Z][A-Za-z].*$                                # (a) Subsection
    )
    """
)


def segment(text: str) -> list[Segment]:
    """
    Split a contract into clause-sized segments.

    Uses heading lines to define boundaries; falls back to paragraph splits
    when no headings are present. Each segment carries absolute char offsets
    for span-accurate persistence.
    """
    if not text or not text.strip():
        return []

    boundaries: list[int] = [0]
    for m in _HEADING_RE.finditer(text):
        boundaries.append(m.start())
    boundaries.append(len(text))
    boundaries = sorted(set(boundaries))

    segments: list[Segment] = []
    for i in range(len(boundaries) - 1):
        s, e = boundaries[i], boundaries[i + 1]
        body = text[s:e].strip()
        if not body:
            continue
        # Drop pure-heading slivers
        if len(body) < 60 and "\n" not in body:
            continue
        segments.append(Segment(text=body, start=s, end=e))

    if len(segments) < 3:
        # Heading-light contract — fall back to blank-line split.
        segments = []
        cursor = 0
        for chunk in re.split(r"\n\s*\n", text):
            stripped = chunk.strip()
            if stripped and len(stripped) > 60:
                start = text.find(chunk, cursor)
                start = start if start >= 0 else cursor
                segments.append(Segment(text=stripped, start=start, end=start + len(chunk)))
                cursor = start + len(chunk)

    return segments


# =============================================================================
# Similarity
# =============================================================================


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = 0.0
    da = 0.0
    db = 0.0
    for x, y in zip(a, b):
        num += x * y
        da += x * x
        db += y * y
    if da == 0.0 or db == 0.0:
        return 0.0
    return num / (da**0.5 * db**0.5)


def keyword_overlap(text: str, required: list[str]) -> float:
    if not required:
        return 0.0
    lower = text.lower()
    hits = sum(1 for kw in required if kw.lower() in lower)
    return hits / len(required)


# =============================================================================
# Sub-element detection
# =============================================================================

# Specific regex helpers for high-value sub-elements that recur across clauses.
_SUB_ELEMENT_PATTERNS: dict[str, list[re.Pattern]] = {
    "aggregate_cap": [
        re.compile(r"(?i)\b(?:total|aggregate)\s+liability\b.{0,80}?(?:exceed|cap|limited)"),
        re.compile(r"(?i)liability\s+(?:shall|will)\s+not\s+exceed"),
    ],
    "consequential_exclusion": [
        re.compile(r"(?i)\b(?:indirect|incidental|consequential|special|punitive)\b"),
        re.compile(r"(?i)lost\s+(?:profits|revenue|data)"),
    ],
    "carveouts": [
        re.compile(r"(?i)except(?:ing)?\s+(?:for|that)"),
        re.compile(r"(?i)(?:gross negligence|willful misconduct|fraud)"),
    ],
    "mutual": [
        re.compile(r"(?i)(?:each|either|both)\s+part(?:y|ies)"),
        re.compile(r"(?i)mutual"),
    ],
    "scope": [re.compile(r"(?i)scope")],
    "procedure": [
        re.compile(r"(?i)(?:notice|notify)"),
        re.compile(r"(?i)control\s+(?:of|over)\s+(?:the\s+)?defense"),
    ],
    "exclusive_remedy": [re.compile(r"(?i)sole\s+(?:and\s+)?exclusive\s+remedy")],
    "as_is": [re.compile(r"(?i)\bAS\s+IS\b")],
    "implied_disclaimed": [
        re.compile(r"(?i)merchantability"),
        re.compile(r"(?i)fitness\s+for\s+(?:a\s+)?particular\s+purpose"),
    ],
    "present_assignment": [re.compile(r"(?i)hereby\s+(?:irrevocably\s+)?assigns?")],
    "moral_rights_waiver": [re.compile(r"(?i)moral\s+rights")],
    "further_assurances": [re.compile(r"(?i)further\s+assurances?")],
    "scope_grant": [
        re.compile(r"(?i)(?:non[\s-]?exclusive|exclusive|perpetual|irrevocable|royalty[\s-]?free)")
    ],
    "field_of_use": [re.compile(r"(?i)solely\s+for|internal\s+business\s+purposes")],
    "term_territory": [re.compile(r"(?i)(?:worldwide|territory|term)")],
    "perpetual_irrevocable": [re.compile(r"(?i)perpetual,?\s+irrevocable")],
    "no_obligation": [re.compile(r"(?i)no\s+obligation")],
    "definition": [re.compile(r"(?i)\"Confidential Information\"\s+means")],
    "exclusions": [
        re.compile(r"(?i)publicly\s+available"),
        re.compile(r"(?i)independently\s+developed"),
    ],
    "term_of_protection": [
        re.compile(r"(?i)\b(?:one|two|three|four|five|\d+)\s+\(?\d*\)?\s+years?\b")
    ],
    "permitted_disclosures": [re.compile(r"(?i)compelled\s+(?:to\s+)?(?:disclose|by\s+law)")],
    "initial_term": [re.compile(r"(?i)initial\s+term")],
    "renewal": [re.compile(r"(?i)(?:automatically\s+)?renew")],
    "non_renewal_notice": [re.compile(r"(?i)(?:non[\s-]?renewal|notice\s+of\s+non[\s-]?renewal)")],
    "notice_period": [
        re.compile(
            r"(?i)(?:thirty|sixty|ninety|\d+)\s*\(?\d*\)?\s*days?\s+(?:prior\s+)?(?:written\s+)?notice"
        )
    ],
    "fee": [re.compile(r"(?i)termination\s+fee")],
    "material_breach": [re.compile(r"(?i)material\s+breach")],
    "cure_period": [re.compile(r"(?i)fails?\s+to\s+cure|cure\s+period")],
    "insolvency": [re.compile(r"(?i)(?:insolven|bankrupt|receiver)")],
    "survival": [re.compile(r"(?i)(?:shall\s+)?survive\s+(?:the\s+)?(?:termination|expiration)")],
    "return_or_destroy": [re.compile(r"(?i)return\s+or\s+destroy")],
    "refund": [re.compile(r"(?i)refund\s+.{0,40}prepaid|pro[\s-]?rata\s+refund")],
    "due_period": [re.compile(r"(?i)net\s+(?:thirty|sixty|\d+)")],
    "late_fee": [re.compile(r"(?i)(?:late\s+(?:fee|payment)|interest\s+at)")],
    "taxes": [re.compile(r"(?i)tax(?:es|able)")],
    "disputes": [re.compile(r"(?i)disput(?:e|ed\s+(?:invoice|amount))")],
    "cap": [re.compile(r"(?i)not\s+(?:to\s+)?exceed\s+\d|CPI|\d+\s*%")],
    "notice": [re.compile(r"(?i)\d+\s+days?\s+(?:prior\s+)?(?:written\s+)?notice")],
    "standards": [re.compile(r"(?i)(?:SOC\s*2|ISO[\s/-]?27001|NIST)")],
    "encryption": [re.compile(r"(?i)encrypt")],
    "incident_notification": [
        re.compile(r"(?i)(?:security\s+incident|data\s+breach|unauthorized\s+access)")
    ],
    "dpa_incorporated": [re.compile(r"(?i)data\s+processing\s+(?:addendum|agreement)|\bDPA\b")],
    "scc_reference": [re.compile(r"(?i)standard\s+contractual\s+clauses")],
    "jurisdiction_named": [
        re.compile(r"(?i)laws?\s+of\s+(?:the\s+)?(?:state\s+of\s+)?[A-Z][a-zA-Z ]+")
    ],
    "conflict_of_laws_excluded": [
        re.compile(r"(?i)without\s+regard\s+to\s+(?:its\s+)?conflicts?\s+of\s+laws?")
    ],
    "uncisg_excluded": [re.compile(r"(?i)international\s+sale\s+of\s+goods")],
    "exclusive": [re.compile(r"(?i)exclusive\s+jurisdiction")],
    "specific_courts": [re.compile(r"(?i)state\s+and\s+federal\s+courts")],
    "rules_administrator": [re.compile(r"(?i)\b(?:JAMS|AAA|ICC|ICDR)\b")],
    "seat": [re.compile(r"(?i)seat\s+of\s+arbitration")],
    "language": [re.compile(r"(?i)language\s+(?:of|shall\s+be)")],
    "class_waiver": [re.compile(r"(?i)class[\s-]?action\s+waiver|class.{0,30}waiver")],
    "ip_carveout": [re.compile(r"(?i)(?:injunct|equitable\s+relief)")],
    "conspicuous": [re.compile(r"WAIVES?\s+(?:THE\s+)?(?:RIGHT\s+TO\s+)?(?:TRIAL\s+BY\s+)?JURY")],
    "duration": [
        re.compile(r"(?i)(?:twelve|six|twenty[\s-]?four|\d+)\s+(?:\(\d+\)\s+)?(?:months?|years?)")
    ],
    "geography": [
        re.compile(
            r"(?i)(?:within|in)\s+(?:the\s+)?(?:United\s+States|[A-Z][a-z]+\s+(?:County|state))|geographic"
        )
    ],
    "scope_of_activity": [re.compile(r"(?i)(?:competes?|compete\s+with|engage\s+in)")],
    "consideration": [re.compile(r"(?i)(?:adequate\s+)?consideration")],
    "scope_targets": [re.compile(r"(?i)(?:employees?|customers?|clients?)")],
    "general_advertising_carveout": [re.compile(r"(?i)general\s+(?:advertising|public)")],
    "consent_required": [re.compile(r"(?i)prior\s+written\s+consent")],
    "affiliate_carveout": [
        re.compile(r"(?i)affiliate|merger,?\s+acquisition|change\s+of\s+control")
    ],
    "void_if_violated": [
        re.compile(r"(?i)(?:purported\s+assignment.{0,30}void|void\s+(?:ab\s+initio|under)?)")
    ],
    "covered_events": [re.compile(r"(?i)(?:acts?\s+of\s+god|war|pandemic|terror|government)")],
    "payment_carveout": [re.compile(r"(?i)(?:other\s+than\s+payment|except\s+for\s+payment)")],
    "termination_after_extended_event": [
        re.compile(r"(?i)\d+\s+days?\s+.{0,40}terminate|continues?\s+for\s+more\s+than")
    ],
    "integration": [re.compile(r"(?i)(?:supersedes?|entire\s+agreement)")],
    "no_oral_modification": [
        re.compile(r"(?i)(?:in\s+writing|written\s+(?:and\s+signed|amendment))")
    ],
    "blue_pencil": [re.compile(r"(?i)(?:reform|modif(?:y|ied)\s+to\s+the\s+(?:minimum|extent))")],
    "addresses": [
        re.compile(r"(?i)addresses?\s+(?:set\s+forth|specified|designated|on\s+the\s+signature)")
    ],
    "methods": [re.compile(r"(?i)(?:overnight\s+courier|certified\s+mail|email)")],
    "frequency": [re.compile(r"(?i)(?:once\s+per\s+(?:twelve|year)|not\s+more\s+than)")],
    "cost_allocation": [re.compile(r"(?i)(?:bear\s+the\s+cost|reimburse\s+.{0,30}audit)")],
    "esign_recognized": [re.compile(r"(?i)(?:electronic\s+signature|DocuSign)")],
    "us_export_compliance": [re.compile(r"(?i)(?:export\s+administration|EAR\b|OFAC)")],
    "embargo_certification": [re.compile(r"(?i)(?:sanction|embargo|restricted[\s-]?part)")],
    "fcpa_compliance": [re.compile(r"(?i)(?:FCPA|foreign\s+corrupt|bribery\s+act)")],
    "types": [
        re.compile(
            r"(?i)(?:CGL|commercial\s+general|errors\s+and\s+omissions|cyber|workers'?\s+comp)"
        )
    ],
    "minimums": [re.compile(r"(?i)\$[\d,]+(?:,000)?(?:\s+per\s+(?:occurrence|claim))?")],
    "additional_insured": [re.compile(r"(?i)additional\s+insured")],
    "royalty": [re.compile(r"(?i)royalt(?:y|ies|y[\s-]?free)")],
}


def detect_sub_elements(text: str, canonical: dict) -> list[str]:
    detected: list[str] = []
    lower = text.lower()
    for sub in canonical.get("sub_elements") or []:
        key = sub["key"]
        patterns = _SUB_ELEMENT_PATTERNS.get(key)
        if patterns:
            if any(p.search(text) for p in patterns):
                detected.append(key)
                continue
        # Fallback: name-keyword presence
        name_words = [w.lower() for w in sub["name"].split() if len(w) > 4]
        if name_words and all(w in lower for w in name_words):
            detected.append(key)
    return detected


# =============================================================================
# Main classifier
# =============================================================================


class ClauseClassifier:
    """
    Pure-Python clause classifier.

    Constructor takes the cached canonical embeddings (loaded once); call
    `classify(text, embed_fn)` per document. `embed_fn` is an async callable
    that maps list[str] -> list[list[float]] — typically the embedding service.
    """

    def __init__(self, canonicals: list[dict]):
        self._canonicals = canonicals
        self._compiled_anchors: dict[str, list[re.Pattern]] = {}
        for c in canonicals:
            self._compiled_anchors[c["slug"]] = [
                re.compile(p, re.IGNORECASE) for p in (c.get("regex_anchors") or [])
            ]

    @classmethod
    async def from_db(cls, session: AsyncSession) -> ClauseClassifier:
        result = await session.execute(select(ClauseCanonical))
        rows = result.scalars().all()
        canonicals: list[dict] = []
        for r in rows:
            canonicals.append(
                {
                    "id": r.id,
                    "slug": r.slug,
                    "name": r.name,
                    "category": r.category,
                    "sub_elements": r.sub_elements or [],
                    "regex_anchors": r.regex_anchors or [],
                    "required_keywords": r.required_keywords or [],
                    "embedding": r.embedding,
                    "market_standard_text": r.market_standard_text,
                }
            )
        # If DB has no rows, fall back to seed taxonomy (read-only mode for dev).
        if not canonicals:
            canonicals = [{**c, "id": None, "embedding": None} for c in CANONICAL_CLAUSES]
        return cls(canonicals)

    async def classify(
        self,
        text: str,
        embed_segments_fn=None,
    ) -> list[TagCandidate]:
        """
        Classify a contract.

        embed_segments_fn(list[str]) -> list[list[float]] (async). If None,
        falls back to regex+keyword only (degraded but functional).
        """
        segs = segment(text)
        if not segs:
            return []

        # --- Pass 1: regex anchors (high precision) ---
        results: list[TagCandidate] = []
        seg_to_regex_hits: list[set[str]] = [set() for _ in segs]
        for i, seg in enumerate(segs):
            for c in self._canonicals:
                anchors = self._compiled_anchors[c["slug"]]
                if any(a.search(seg.text) for a in anchors):
                    seg_to_regex_hits[i].add(c["slug"])

        # --- Pass 2: embeddings (recall) ---
        seg_embeds: list[list[float]] | None = None
        if embed_segments_fn is not None:
            try:
                seg_embeds = await embed_segments_fn([s.text for s in segs])
            except Exception as e:
                logger.warning(f"Segment embedding failed; falling back to regex-only: {e}")
                seg_embeds = None

        for i, seg in enumerate(segs):
            scored: list[tuple[str, float, str]] = []  # (slug, score, method)

            # Regex hits
            for slug in seg_to_regex_hits[i]:
                scored.append((slug, REGEX_CONFIDENCE, "regex"))

            # Embedding similarity
            if seg_embeds is not None:
                for c in self._canonicals:
                    if c.get("embedding"):
                        sim = cosine(seg_embeds[i], c["embedding"])
                        if sim >= EMBED_THRESHOLD:
                            kw = keyword_overlap(seg.text, c.get("required_keywords") or [])
                            hybrid = 0.7 * sim + 0.3 * kw
                            if hybrid >= HYBRID_THRESHOLD:
                                # Keep best score per slug
                                method = (
                                    "hybrid" if c["slug"] in seg_to_regex_hits[i] else "embedding"
                                )
                                scored.append((c["slug"], max(hybrid, sim), method))

            # Dedup per segment by slug, keep highest score
            best_per_slug: dict[str, tuple[float, str]] = {}
            for slug, score, method in scored:
                cur = best_per_slug.get(slug)
                if cur is None or score > cur[0]:
                    best_per_slug[slug] = (score, method)

            for slug, (score, method) in best_per_slug.items():
                canonical = next((c for c in self._canonicals if c["slug"] == slug), None)
                if not canonical:
                    continue
                detected_subs = detect_sub_elements(seg.text, canonical)
                results.append(
                    TagCandidate(
                        canonical_slug=slug,
                        canonical_id=canonical.get("id"),
                        segment=seg,
                        method=method,
                        confidence=round(score, 3),
                        detected_sub_elements=detected_subs,
                    )
                )

        return results
