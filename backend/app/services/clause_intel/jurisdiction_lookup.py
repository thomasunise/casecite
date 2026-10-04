"""
Jurisdiction enforceability lookup.

Given a list of (canonical_slug, jurisdiction) pairs, returns the structured
rule and any structural issues (e.g., non-compete in CA flagged as void).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clause_intel import ClauseCanonical, ClauseJurisdictionRule
from app.services.clause_intel.jurisdiction_seed import JURISDICTION_RULES


@dataclass
class JurisdictionFlag:
    canonical_slug: str
    jurisdiction: str
    enforceability: str
    severity: str  # critical | major | informational
    note: str | None
    constraints: dict
    authorities: list[dict]
    recommended_text: str | None
    # When the rule was compiled; None for rules that predate the stamp.
    as_of: str | None = None


_SEVERITY_BY_ENFORCEABILITY = {
    "void": "critical",
    "limited": "major",
    "reformable": "major",
    "unsettled": "informational",
    "enforceable": "informational",
}


async def evaluate(
    canonical_slugs: list[str],
    jurisdiction: str,
    session: AsyncSession,
) -> list[JurisdictionFlag]:
    if not jurisdiction or not canonical_slugs:
        return []
    juris_norm = jurisdiction.strip().upper()
    slugs = list({s for s in canonical_slugs if s})

    # Try DB-loaded rules
    db_rules: dict[str, dict] = {}
    if slugs:
        q = (
            select(ClauseJurisdictionRule, ClauseCanonical)
            .join(ClauseCanonical, ClauseJurisdictionRule.canonical_id == ClauseCanonical.id)
            .where(
                ClauseJurisdictionRule.jurisdiction == juris_norm,
                ClauseCanonical.slug.in_(slugs),
            )
        )
        rows = (await session.execute(q)).all()
        for rule, canonical in rows:
            db_rules[canonical.slug] = {
                "enforceability": rule.enforceability,
                "constraints": rule.constraints or {},
                "authorities": rule.authorities or [],
                "note": rule.note,
                "recommended_text": rule.recommended_text,
            }

    # Seed fallback for jurisdictions or slugs not yet in DB
    seed_rules: dict[str, dict] = {}
    for r in JURISDICTION_RULES:
        if r["jurisdiction"].upper() == juris_norm and r["canonical_slug"] in slugs:
            seed_rules[r["canonical_slug"]] = r

    flags: list[JurisdictionFlag] = []
    for slug in slugs:
        rule = db_rules.get(slug) or seed_rules.get(slug)
        if not rule:
            continue
        flags.append(
            JurisdictionFlag(
                canonical_slug=slug,
                jurisdiction=juris_norm,
                enforceability=rule["enforceability"],
                severity=_SEVERITY_BY_ENFORCEABILITY.get(rule["enforceability"], "major"),
                note=rule.get("note"),
                constraints=rule.get("constraints") or {},
                authorities=rule.get("authorities") or [],
                recommended_text=rule.get("recommended_text"),
                as_of=(rule.get("constraints") or {}).get("as_of"),
            )
        )
    return flags
