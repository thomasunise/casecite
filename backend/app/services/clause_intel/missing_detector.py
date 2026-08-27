"""
Missing-clause detector.

Given:
  - The contract type (nda / msa / saas / employment / license / sow / ...)
  - The set of canonical slugs the classifier tagged in the document

Compute:
  - missing_required: slugs that are required for the type and not tagged
  - missing_recommended: slugs that are recommended for the type and not tagged
  - confidence: 1.0 if the type's required/recommended sets are populated;
                0.5 if the type isn't in our requirements table

The output is structured — UI/LLM compose user-facing prose.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clause_intel import ContractTypeRequirement
from app.services.clause_intel.taxonomy_seed import (
    CONTRACT_TYPE_REQUIREMENTS,
    get_canonical_by_slug,
)


@dataclass
class MissingClauseResult:
    contract_type: str
    tagged_slugs: list[str]
    missing_required: list[dict]
    missing_recommended: list[dict]
    coverage_required_pct: float
    coverage_recommended_pct: float
    confidence: float


async def detect_missing(
    contract_type: str,
    tagged_slugs: list[str],
    session: AsyncSession,
) -> MissingClauseResult:
    contract_type_norm = (contract_type or "").strip().lower()

    # Prefer DB-loaded requirements; fall back to seed for unknown types.
    required: list[str] = []
    recommended: list[str] = []
    confidence = 1.0

    if contract_type_norm:
        rows = (
            (
                await session.execute(
                    select(ContractTypeRequirement).where(
                        ContractTypeRequirement.contract_type == contract_type_norm
                    )
                )
            )
            .scalars()
            .all()
        )
        if rows:
            for r in rows:
                if r.requirement == "required":
                    required.append(r.canonical_slug)
                elif r.requirement == "recommended":
                    recommended.append(r.canonical_slug)
        elif contract_type_norm in CONTRACT_TYPE_REQUIREMENTS:
            required = CONTRACT_TYPE_REQUIREMENTS[contract_type_norm].get("required", [])
            recommended = CONTRACT_TYPE_REQUIREMENTS[contract_type_norm].get("recommended", [])
        else:
            confidence = 0.5

    tagged_set = set(tagged_slugs)
    missing_required_slugs = [s for s in required if s not in tagged_set]
    missing_recommended_slugs = [s for s in recommended if s not in tagged_set]

    def _expand(slug: str) -> dict:
        canonical = get_canonical_by_slug(slug)
        return {
            "canonical_slug": slug,
            "name": canonical["name"] if canonical else slug.replace("_", " ").title(),
            "category": canonical["category"] if canonical else "unknown",
            "rationale": canonical.get("description") if canonical else None,
        }

    coverage_req = (
        ((len(required) - len(missing_required_slugs)) / len(required)) if required else 1.0
    )
    coverage_rec = (
        ((len(recommended) - len(missing_recommended_slugs)) / len(recommended))
        if recommended
        else 1.0
    )

    return MissingClauseResult(
        contract_type=contract_type_norm,
        tagged_slugs=sorted(tagged_set),
        missing_required=[_expand(s) for s in missing_required_slugs],
        missing_recommended=[_expand(s) for s in missing_recommended_slugs],
        coverage_required_pct=round(coverage_req * 100, 1),
        coverage_recommended_pct=round(coverage_rec * 100, 1),
        confidence=confidence,
    )
