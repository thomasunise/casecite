"""
Contract Analysis (Phase 2) orchestrator.

Public API:
  analyze(text, contract_type, jurisdiction, effective_date, ...) -> dict

Builds on Phase 1 (clause_intel) for tags / deviations / jurisdiction flags
and adds parties + obligations + deadlines + risk + defined-terms.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.clause_intel import ContractAnalysisRun
from app.models.contract_analysis import (
    ContractDeadline,
    ContractDefinedTerm,
    ContractObligation,
    ContractParty,
)
from app.services.clause_intel import clause_intel_service
from app.services.contract_analysis.ai_review import ai_review_findings
from app.services.contract_analysis.deadlines import extract_deadlines
from app.services.contract_analysis.defined_terms import check_defined_terms
from app.services.contract_analysis.issues import (
    FALLBACK_CONTRACT_TYPE,
    annotate_issues,
    collect_findings,
    detect_contract_type,
    is_absence_claim,
    merge_issues,
    verify_absence_claims,
)
from app.services.contract_analysis.key_terms import extract_key_terms
from app.services.contract_analysis.obligations import extract_obligations, link_deadlines
from app.services.contract_analysis.parties import resolve_parties
from app.services.document_analyzer import document_analyzer_service
from app.services.llm_clients import make_openai

logger = logging.getLogger(__name__)

# Chunks are cut with a 128-token overlap (~500 chars); anything shorter than
# this is not treated as a seam, so ordinary repeated phrases survive.
_MIN_SEAM_OVERLAP = 20
_MAX_SEAM_OVERLAP = 4_000


def merge_overlapping_chunks(texts: list[str]) -> str:
    """Join consecutive chunk texts, dropping the run each chunk repeats from
    the end of the previous one.

    The chunker slices one token stream with an overlap, so the start of chunk
    N+1 is a verbatim suffix of chunk N. Joining naively repeats that run —
    roughly a quarter of every chunk — and the analysis then sees duplicated
    clauses, quotes them twice and redlines them twice. Seams are detected as
    the longest suffix/prefix match of at least ``_MIN_SEAM_OVERLAP`` chars;
    chunks with no such match are joined with a newline as before.
    """
    merged = ""
    for chunk in texts:
        if not chunk:
            continue
        if not merged:
            merged = chunk
            continue
        limit = min(len(merged), len(chunk), _MAX_SEAM_OVERLAP)
        overlap = 0
        for k in range(limit, _MIN_SEAM_OVERLAP - 1, -1):
            if merged.endswith(chunk[:k]):
                overlap = k
                break
        merged = merged + chunk[overlap:] if overlap else merged + "\n" + chunk
    return merged


class ContractAnalysisService:
    """Phase 2 orchestrator."""

    def _api_key(self, user_keys) -> str | None:
        if user_keys and getattr(user_keys, "openai", None):
            return user_keys.openai
        return settings.openai_api_key

    async def resolve_document_text(self, document_id: str, user_id: str) -> str:
        """Load an indexed document's text, tenancy-checked.

        Text is reconstructed from the document's vector-store chunks in
        chunk order. Chunks are cut with a token overlap, so consecutive
        chunks share a run of text at the seam; ``merge_overlapping_chunks``
        drops the repeated run so a clause is not analysed (or quoted, or
        redlined) twice. Quotes and spans in the analysis refer to THIS text,
        which the response also carries, so findings stay self-consistent;
        the tracked-changes export re-anchors them onto the stored original.
        """
        from app.services.documents import document_service
        from app.services.rag.search import get_document_chunks_directly
        from app.services.vectordb import get_vector_db

        doc = await document_service.get_document(document_id, user_id)
        if doc is None:
            raise LookupError("Document not found")
        vector_db = get_vector_db()
        if vector_db is None:
            raise RuntimeError("Document storage is temporarily unavailable")
        chunks = await get_document_chunks_directly(
            vector_db, [document_id], limit=2000, user_id=user_id
        )
        chunks.sort(key=lambda c: c.get("metadata", {}).get("chunk_index", 0))
        text = merge_overlapping_chunks([c.get("text") or "" for c in chunks]).strip()
        if not text:
            raise LookupError("No indexed text is available for this document")
        return text

    async def document_label(self, document_id: str, user_id: str) -> str:
        """Human label for a document — filename, falling back to the id."""
        from app.services.documents import document_service

        doc = await document_service.get_document(document_id, user_id)
        return doc.filename if doc else document_id

    async def persist_redlines(
        self, analysis_id: str, edits: list[dict[str, Any]], text_len: int
    ) -> None:
        """Store generated redlines on the run so the tracked-changes export
        can rebuild the document later. ``text_len`` guards against exporting
        against a re-indexed (shifted-offset) document."""
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    select(ContractAnalysisRun).where(ContractAnalysisRun.id == analysis_id)
                )
            ).scalar_one_or_none()
            if not row:
                return
            summary = dict(row.summary or {})
            summary["redlines"] = edits
            summary["redline_text_len"] = text_len
            row.summary = summary
            await session.commit()

    async def analyze(
        self,
        text: str,
        contract_type: str | None = "auto",
        jurisdiction: str | None = None,
        effective_date: datetime | None = None,
        user_id: str | None = None,
        document_id: str | None = None,
        user_keys=None,
        representing: str | None = None,
        posture: str = "balanced",
        instructions: str | None = None,
    ) -> dict[str, Any]:
        if not text or not text.strip():
            raise ValueError("Document text is required")

        posture = (posture or "balanced").strip().lower()
        if posture not in ("strict", "balanced"):
            posture = "balanced"
        representing = (representing or "").strip() or None

        llm_client = make_openai(self._api_key(user_keys), async_=True)

        # Auto-detect the contract type when not supplied.
        contract_type = (contract_type or "").strip().lower()
        if not contract_type or contract_type == "auto":
            if llm_client is not None:
                contract_type = await detect_contract_type(llm_client, text)
            else:
                contract_type = FALLBACK_CONTRACT_TYPE

        # Phase 1: clause intel (writes its own ContractAnalysisRun)
        clause_result = await clause_intel_service.analyze_contract(
            text=text,
            contract_type=contract_type,
            jurisdiction=jurisdiction,
            user_id=user_id,
            document_id=document_id,
            user_keys=user_keys,
        )
        analysis_id = clause_result["analysis_id"]

        # Phase 2 — pure rule extractors
        parties = resolve_parties(text)
        obligations = extract_obligations(text, parties)
        deadlines = extract_deadlines(text, effective_date=effective_date)
        link_deadlines(obligations, deadlines)
        defined_terms = check_defined_terms(text)

        # NO built-in clause library or canned risk rules in the judgment
        # path. What counts as an issue is decided by the AI review against
        # the USER'S instructions — the seeded clause tags survive only as
        # neutral text locators (key terms anchoring), never as judgments.
        # There is deliberately no risk score: issues are listed, not graded.
        party_dicts = [
            {
                "canonical_name": p.canonical_name,
                "role": p.role,
                "aliases": p.aliases,
                "detection_method": p.detection_method,
                "confidence": p.confidence,
                "first_span_start": p.first_span_start,
                "first_span_end": p.first_span_end,
            }
            for p in parties
        ]

        # General-purpose LLM contract analysis. Runs for EVERY document —
        # never gated on the seeded contract-type taxonomy — so unknown types
        # ("other", e.g. a residential lease) still get substantive findings.
        # Never fatal: any failure degrades to rules-only findings.
        general_analysis: dict[str, Any] | None = None
        try:
            general_analysis = await document_analyzer_service.analyze_contract(
                document_text=text,
                document_name=None,
                user_id=user_id,
                user_keys=user_keys,
            )
        except Exception as e:
            logger.warning("general contract analysis failed; continuing rules-only: %s", e)
            general_analysis = None
        if not isinstance(general_analysis, dict):
            general_analysis = None
        elif general_analysis.get("error"):
            logger.warning(
                "general contract analysis returned error; continuing rules-only: %s",
                general_analysis.get("error"),
            )
            general_analysis = None

        executive_summary: str | None = None
        if general_analysis:
            raw_summary = general_analysis.get("summary")
            if isinstance(raw_summary, str) and raw_summary.strip():
                executive_summary = raw_summary.strip()

        # Unified direction-aware issues report. Never fatal: LLM failure (or no
        # client) degrades to the mechanical issue list.
        findings = collect_findings(
            {"deviations": [], "missing": {}, "jurisdiction_flags": []},
            general_analysis,
        )

        # AI-first review: the model reads THIS contract against the user's
        # instructions and adds whatever the fixed detectors missed — every
        # finding verbatim-grounded or discarded. The library is supplementary;
        # the instructions are primary.
        if llm_client is not None:
            try:
                existing_spans = [
                    (f["span_start"], f["span_end"])
                    for f in findings
                    if f.get("span_start") is not None and f.get("span_end") is not None
                ]
                findings.extend(
                    await ai_review_findings(
                        llm_client, text, instructions, contract_type, existing_spans
                    )
                )
            except Exception as e:  # never fatal
                logger.warning("AI review pass failed; continuing with rule findings: %s", e)
        llm_payload = None
        if llm_client is not None and findings:
            llm_payload = await annotate_issues(
                llm_client,
                findings=findings,
                parties=[
                    {"canonical_name": p["canonical_name"], "role": p["role"]} for p in party_dicts
                ],
                representing=representing,
                posture=posture,
                contract_type=contract_type,
                instructions=instructions,
            )
        issues = merge_issues(findings, llm_payload)

        # Grounding discipline: an issue either points at real text (span from a
        # rule/tag), reports an absence (missing clause — nothing to point at),
        # or is an unverified model conclusion. The UI renders these differently
        # and never presents an unverified finding as sourced.
        for issue in issues:
            if issue.get("span_start") is not None:
                issue["grounding"] = "span"
            elif is_absence_claim(issue):
                issue["grounding"] = "absence"
            else:
                issue["grounding"] = "unverified"

        # An accusation of absence must survive verification against the
        # document before anyone sees it (or a redline proposes "adding" a
        # clause the contract already has).
        if llm_client is not None and issues:
            issues = await verify_absence_claims(llm_client, text, issues)

        # Structured key-terms table, clause-tag-anchored and quote-verified.
        key_terms: dict[str, Any] = {}
        if llm_client is not None:
            try:
                key_terms = await extract_key_terms(llm_client, text, clause_result.get("tags", []))
            except Exception as e:  # enhancement, never fatal
                logger.warning("key-terms extraction failed; continuing without: %s", e)

        # Persist Phase 2 records (analysis_id row already created by Phase 1)
        async with AsyncSessionLocal() as session:
            # Update parent run with the Phase 2 summary
            row = (
                await session.execute(
                    select(ContractAnalysisRun).where(ContractAnalysisRun.id == analysis_id)
                )
            ).scalar_one_or_none()
            if row:
                summary = dict(row.summary or {})
                summary["parties"] = len(parties)
                summary["obligations"] = len(obligations)
                summary["deadlines"] = len(deadlines)
                summary["defined_terms"] = len(defined_terms)
                summary["contract_type"] = contract_type
                summary["representing"] = representing
                summary["posture"] = posture
                summary["instructions"] = instructions
                summary["issues"] = issues
                summary["executive_summary"] = executive_summary
                summary["key_terms"] = key_terms
                row.summary = summary

            party_id_by_name: dict[str, int] = {}
            for p in parties:
                pr = ContractParty(
                    analysis_id=analysis_id,
                    canonical_name=p.canonical_name,
                    role=p.role,
                    aliases=p.aliases,
                    first_span_start=p.first_span_start,
                    first_span_end=p.first_span_end,
                    detection_method=p.detection_method,
                    confidence=p.confidence,
                )
                session.add(pr)
                await session.flush()
                party_id_by_name[p.canonical_name] = pr.id

            for o in obligations:
                session.add(
                    ContractObligation(
                        analysis_id=analysis_id,
                        subject_party=o.subject_party,
                        subject_party_id=party_id_by_name.get(o.subject_party or ""),
                        modal=o.modal,
                        action=o.action,
                        object_text=o.object_text,
                        conditions=o.conditions,
                        deadlines=o.deadlines,
                        span_start=o.span_start,
                        span_end=o.span_end,
                        matched_text=o.matched_text,
                        category=o.category,
                        is_unilateral=1 if o.is_unilateral else 0,
                        is_perpetual=1 if o.is_perpetual else 0,
                        is_continuing=1 if o.is_continuing else 0,
                        detection_method=o.detection_method,
                        confidence=o.confidence,
                    )
                )

            for d in deadlines:
                session.add(
                    ContractDeadline(
                        analysis_id=analysis_id,
                        kind=d.kind,
                        description=d.description,
                        anchor=d.anchor,
                        offset_days=d.offset_days,
                        period_days=d.period_days,
                        resolved_date=d.resolved_date,
                        span_start=d.span_start,
                        span_end=d.span_end,
                        matched_text=d.matched_text,
                    )
                )

            for t in defined_terms:
                session.add(
                    ContractDefinedTerm(
                        analysis_id=analysis_id,
                        term=t.term,
                        definition_text=t.definition_text,
                        defined=1 if t.defined else 0,
                        usage_count=t.usage_count,
                        used_but_undefined=1 if t.used_but_undefined else 0,
                        defined_but_unused=1 if t.defined_but_unused else 0,
                        circular_reference=1 if t.circular_reference else 0,
                        span_start=t.span_start,
                        span_end=t.span_end,
                    )
                )

            await session.commit()

        return {
            "analysis_id": analysis_id,
            "phase1": clause_result,
            "contract_type": contract_type,
            "representing": representing,
            "posture": posture,
            "issues": issues,
            "executive_summary": executive_summary,
            "key_terms": key_terms,
            "parties": party_dicts,
            "obligations": [
                {
                    "subject_party": o.subject_party,
                    "modal": o.modal,
                    "action": o.action,
                    "object_text": o.object_text,
                    "conditions": o.conditions,
                    "category": o.category,
                    "is_unilateral": o.is_unilateral,
                    "is_perpetual": o.is_perpetual,
                    "is_continuing": o.is_continuing,
                    "span_start": o.span_start,
                    "span_end": o.span_end,
                    "matched_text": o.matched_text,
                    "confidence": o.confidence,
                }
                for o in obligations
            ],
            "deadlines": [
                {
                    "kind": d.kind,
                    "description": d.description,
                    "anchor": d.anchor,
                    "offset_days": d.offset_days,
                    "period_days": d.period_days,
                    "resolved_date": d.resolved_date.isoformat() if d.resolved_date else None,
                    "matched_text": d.matched_text,
                    "span_start": d.span_start,
                    "span_end": d.span_end,
                }
                for d in deadlines
            ],
            "defined_terms": [
                {
                    "term": t.term,
                    "definition_text": t.definition_text,
                    "defined": t.defined,
                    "usage_count": t.usage_count,
                    "used_but_undefined": t.used_but_undefined,
                    "defined_but_unused": t.defined_but_unused,
                    "circular_reference": t.circular_reference,
                }
                for t in defined_terms
            ],
            "summary": {
                "instructions": instructions,
                "parties": len(parties),
                "obligations": len(obligations),
                "deadlines": len(deadlines),
                "defined_terms": len(defined_terms),
                "used_but_undefined": sum(1 for t in defined_terms if t.used_but_undefined),
                "defined_but_unused": sum(1 for t in defined_terms if t.defined_but_unused),
                "circular_references": sum(1 for t in defined_terms if t.circular_reference),
            },
        }


contract_analysis_service = ContractAnalysisService()
