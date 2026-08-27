"""
Clause Intelligence orchestrator.

Public API:
  analyze_contract(text, contract_type, jurisdiction, ...)
      → dict with: tags, missing, deviations, jurisdiction_flags, summary

The orchestrator does no LLM detection — it composes the classifier,
missing-clause detector, deviation detector, and jurisdiction lookup.
The optional LLM layer is used only to *explain* findings the rule
engine has already identified.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.clause_intel import (
    ClauseCanonical,
    ClauseDeviationFinding,
    ClauseTagFinding,
    ContractAnalysisRun,
)
from app.services.clause_intel.classifier import ClauseClassifier
from app.services.clause_intel.deviation_detector import detect_deviations
from app.services.clause_intel.jurisdiction_lookup import evaluate as evaluate_jurisdiction
from app.services.clause_intel.missing_detector import detect_missing
from app.services.embeddings import embedding_service

logger = logging.getLogger(__name__)


class ClauseIntelService:
    """Orchestrator for Phase 1 clause intelligence."""

    async def analyze_contract(
        self,
        text: str,
        contract_type: str,
        jurisdiction: str | None = None,
        user_id: str | None = None,
        document_id: str | None = None,
        user_keys=None,
        persist: bool = True,
    ) -> dict[str, Any]:
        if not text or not text.strip():
            raise ValueError("Document text is required")
        if not contract_type:
            raise ValueError("contract_type is required")

        analysis_id = uuid.uuid4().hex

        async with AsyncSessionLocal() as session:
            # 1. Classify clauses
            classifier = await ClauseClassifier.from_db(session)

            async def embed_fn(segs: list[str]):
                return await embedding_service.embed_texts(segs, user_keys=user_keys)

            tags = await classifier.classify(text, embed_segments_fn=embed_fn)

            # Best tag per (slug, span) — drop dups
            best: dict[tuple[str, int, int], Any] = {}
            for t in tags:
                key = (t.canonical_slug, t.segment.start, t.segment.end)
                cur = best.get(key)
                if cur is None or t.confidence > cur.confidence:
                    best[key] = t
            tags = list(best.values())

            tagged_slugs = sorted({t.canonical_slug for t in tags})

            # 2. Missing clauses
            missing = await detect_missing(contract_type, tagged_slugs, session)

            # 3. Deviations
            canonical_rows = (
                (
                    await session.execute(
                        select(ClauseCanonical).where(ClauseCanonical.slug.in_(tagged_slugs))
                    )
                )
                .scalars()
                .all()
            )
            canonical_index = {
                c.slug: {
                    "id": c.id,
                    "slug": c.slug,
                    "name": c.name,
                    "sub_elements": c.sub_elements or [],
                    "market_standard_text": c.market_standard_text,
                }
                for c in canonical_rows
            }

            deviations: list[Any] = []
            for tag in tags:
                canonical = canonical_index.get(tag.canonical_slug)
                if canonical is None:
                    continue
                deviations.extend(
                    detect_deviations(
                        canonical=canonical,
                        matched_text=tag.segment.text,
                        detected_sub_elements=tag.detected_sub_elements,
                        span_start=tag.segment.start,
                        span_end=tag.segment.end,
                        classifier_confidence=tag.confidence,
                    )
                )

            # 4. Jurisdiction enforceability flags
            jurisdiction_flags = await evaluate_jurisdiction(
                tagged_slugs, jurisdiction or "", session
            )

            # 5. Persist
            if persist:
                run = ContractAnalysisRun(
                    id=analysis_id,
                    user_id=user_id,
                    document_id=document_id,
                    contract_type=contract_type,
                    jurisdiction=(jurisdiction or "").upper() or None,
                    document_length_chars=len(text),
                    tags_found=len(tags),
                    deviations_found=len(deviations),
                    missing_required=len(missing.missing_required),
                    summary={
                        "coverage_required_pct": missing.coverage_required_pct,
                        "coverage_recommended_pct": missing.coverage_recommended_pct,
                    },
                    is_complete=True,
                    completed_at=datetime.utcnow(),
                )
                session.add(run)

                for tag in tags:
                    session.add(
                        ClauseTagFinding(
                            analysis_id=analysis_id,
                            canonical_id=tag.canonical_id,
                            canonical_slug=tag.canonical_slug,
                            span_start=tag.segment.start,
                            span_end=tag.segment.end,
                            matched_text=tag.segment.text[:4000],
                            method=tag.method,
                            confidence=tag.confidence,
                            detected_sub_elements=tag.detected_sub_elements,
                        )
                    )
                for d in deviations:
                    session.add(
                        ClauseDeviationFinding(
                            analysis_id=analysis_id,
                            canonical_id=d.canonical_id,
                            canonical_slug=d.canonical_slug,
                            span_start=d.span_start,
                            span_end=d.span_end,
                            matched_text=d.matched_text,
                            deviation_type=d.deviation_type,
                            sub_element=d.sub_element,
                            severity=d.severity,
                            detail=d.detail,
                            classifier_confidence=d.classifier_confidence,
                        )
                    )
                await session.commit()

        # Compose response
        severity_counts: dict[str, int] = {}
        for d in deviations:
            severity_counts[d.severity] = severity_counts.get(d.severity, 0) + 1

        return {
            "analysis_id": analysis_id,
            "contract_type": contract_type,
            "jurisdiction": jurisdiction,
            "document_length_chars": len(text),
            "tags": [
                {
                    "canonical_slug": t.canonical_slug,
                    "span_start": t.segment.start,
                    "span_end": t.segment.end,
                    "matched_text": t.segment.text[:600],
                    "method": t.method,
                    "confidence": t.confidence,
                    "detected_sub_elements": t.detected_sub_elements,
                }
                for t in tags
            ],
            "missing": {
                "missing_required": missing.missing_required,
                "missing_recommended": missing.missing_recommended,
                "coverage_required_pct": missing.coverage_required_pct,
                "coverage_recommended_pct": missing.coverage_recommended_pct,
                "confidence": missing.confidence,
            },
            "deviations": [
                {
                    "canonical_slug": d.canonical_slug,
                    "deviation_type": d.deviation_type,
                    "sub_element": d.sub_element,
                    "severity": d.severity,
                    "span_start": d.span_start,
                    "span_end": d.span_end,
                    "matched_text": d.matched_text,
                    "detail": d.detail,
                    "classifier_confidence": d.classifier_confidence,
                }
                for d in deviations
            ],
            "jurisdiction_flags": [
                {
                    "canonical_slug": f.canonical_slug,
                    "jurisdiction": f.jurisdiction,
                    "enforceability": f.enforceability,
                    "severity": f.severity,
                    "note": f.note,
                    "constraints": f.constraints,
                    "authorities": f.authorities,
                    "recommended_text": f.recommended_text,
                }
                for f in jurisdiction_flags
            ],
            "summary": {
                "tags_found": len(tags),
                "deviations_found": len(deviations),
                "deviations_by_severity": severity_counts,
                "missing_required": len(missing.missing_required),
                "missing_recommended": len(missing.missing_recommended),
                "jurisdiction_flags": len(jurisdiction_flags),
            },
        }

    async def explain_deviation(
        self,
        deviation: dict,
        canonical_slug: str,
        user_keys=None,
    ) -> str:
        """
        LLM is allowed only to *explain* a rule-engine finding in plain English.
        Returns one paragraph; never used for detection.
        """
        try:
            api_key = None
            if user_keys and getattr(user_keys, "openai", None):
                api_key = user_keys.openai
            else:
                from app.config import settings

                api_key = settings.openai_api_key
            from app.services.llm_clients import make_openai, openai_chat, utility_model
            from app.services.rag.prompt_safety import UNTRUSTED_CONTENT_RULE, untrusted_block

            client = make_openai(api_key, async_=True)
            if client is None:
                return ""
            prompt = (
                "You are explaining a contract deviation to a transactional attorney. "
                "The deviation has already been detected by a rule engine — do NOT "
                "re-evaluate whether it is a deviation. Explain in 2-3 sentences what "
                "the practical risk is and what a market-standard fix looks like.\n\n"
                f"{UNTRUSTED_CONTENT_RULE}\n\n"
                f"Clause type: {canonical_slug}\n"
                f"Deviation: {deviation.get('deviation_type')}\n"
                f"Sub-element: {deviation.get('sub_element')}\n"
                f"Severity: {deviation.get('severity')}\n"
                f"Detail: {deviation.get('detail')}\n"
                "Excerpt:\n"
                + untrusted_block("Contract excerpt", deviation.get("matched_text", "")[:400])
                + "\n"
            )
            resp = await openai_chat(
                client,
                model=utility_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            logger.warning(f"explain_deviation failed: {e}")
            return ""


clause_intel_service = ClauseIntelService()
