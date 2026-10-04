"""
Contract Analysis Router (Phase 2).
"""

import io
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.clause_intel import (
    ClauseDeviationFinding,
    ClauseTagFinding,
    ContractAnalysisRun,
)
from app.models.contract_analysis import (
    ContractDeadline,
    ContractDefinedTerm,
    ContractObligation,
    ContractParty,
)
from app.models.schemas import (
    CompareRequest,
    ContractChatRequest,
    DraftExportRequest,
    DraftGenerateRequest,
    DraftPlanRequest,
    FullAnalyzeRequest,
    PracticeProfileRequest,
    RedlineExportRequest,
)
from app.routers._matter_deps import accessible_matter_ids
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData
from app.services.contract_analysis import contract_analysis_service
from app.services.contract_analysis.chat import answer_contract_question, route_contract_message
from app.services.contract_analysis.compare import compare_contracts
from app.services.contract_analysis.drafting import draft_document, render_draft_docx
from app.services.contract_analysis.long_drafting import (
    generate_from_plan,
    normalize_plan,
    plan_document,
    revise_draft,
)
from app.services.contract_analysis.redlines import (
    generate_redlines,
    reconstruct_original_text,
    relocate_edits,
    render_redline_docx,
)
from app.services.contract_analysis.report import render_docx, render_markdown
from app.services.documents import document_service
from app.services.job_queue import RETRY_POLICIES, RetryPolicy, job_manager
from app.services.llm_clients import make_openai
from app.services.permissions import require_permission
from app.services.user_keys import UserAPIKeys
from app.services.user_settings import load_user_settings
from app.utils.error_handler import handle_service_error
from app.utils.ip_resolution import get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contract-analysis", tags=["contract-analysis"])


def _run_accessible(run, user_id: str, accessible_matter_ids: set[str] | None) -> bool:
    """Access rule for a run: owner, or a member of the run's matter."""
    if run.user_id and run.user_id == user_id:
        return True
    return bool(accessible_matter_ids and run.matter_id and run.matter_id in accessible_matter_ids)


async def _audit(
    http_request: Request,
    current_user: TokenData,
    event_type: AuditEventType,
    action: str,
    analysis_id: str | None = None,
    **details,
) -> None:
    """Audit a read/export/delete of contract work product (ids only, no text)."""
    await audit_service.log_event(
        event_type=event_type,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="contract_analysis",
        resource_id=analysis_id,
        ip_address=get_client_ip(http_request),
        details={"action": action, **details},
    )


@router.post("/analyze")
async def analyze_contract_full(
    request: FullAnalyzeRequest,
    http_request: Request,
    current_user: TokenData = require_permission("contracts.use"),
    async_mode: bool = Query(False, alias="async"),
):
    """Run the full Phase 1 + Phase 2 contract pipeline.

    Preferred input is ``document_id`` — the text is loaded server-side from
    the user's own indexed documents (tenancy-checked). ``document_text`` is
    the secondary path for pasted/unindexed contracts. ``?async=true``
    returns 202 + a job to poll — the pipeline makes several LLM calls.
    """
    eff_date = None
    if request.effective_date:
        try:
            eff_date = datetime.fromisoformat(request.effective_date)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid effective_date: {e}")

    text = (request.document_text or "").strip()
    if request.document_id:
        try:
            text = await contract_analysis_service.resolve_document_text(
                request.document_id, current_user.user_id
            )
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
    if not text:
        raise HTTPException(status_code=400, detail="Provide document_id or document_text.")

    user_keys = UserAPIKeys.from_request(http_request, user_id=current_user.user_id)
    user_id = current_user.user_id
    user_email = current_user.email

    async def do_work():
        result = await contract_analysis_service.analyze(
            text=text,
            contract_type=request.contract_type,
            jurisdiction=request.jurisdiction,
            effective_date=eff_date,
            user_id=user_id,
            document_id=request.document_id,
            user_keys=user_keys,
            representing=request.representing,
            posture=request.posture,
        )
        await audit_service.log_event(
            event_type=AuditEventType.DATA_ACCESS,
            user_id=user_id,
            user_email=user_email,
            details={
                "action": "contract_analysis_full",
                "analysis_id": result["analysis_id"],
                "contract_type": result.get("contract_type"),
                "jurisdiction": request.jurisdiction,
                "issues": len(result.get("issues") or []),
            },
        )
        return result

    if async_mode:
        job_id = await job_manager.submit(
            do_work,
            user_id=user_id,
            endpoint="/contract-analysis/analyze",
            retry_policy=RETRY_POLICIES["ai_analysis"],
        )
        return JSONResponse(
            status_code=202,
            content={"job_id": job_id, "poll_url": f"/api/v1/jobs/{job_id}"},
        )

    try:
        return await do_work()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise handle_service_error(e, "Analysis failed", logger)


def _llm_client(http_request: Request, user_id: str):
    """The user's OpenAI-compatible client (BYOK key, else the instance key)."""
    user_keys = UserAPIKeys.from_request(http_request, user_id=user_id)
    client = make_openai(
        user_keys.openai if user_keys and user_keys.openai else settings.openai_api_key,
        async_=True,
    )
    if client is None:
        raise HTTPException(
            status_code=400,
            detail="An OpenAI API key or a custom LLM endpoint is required. "
            "Configure one in Settings.",
        )
    return client, user_keys


def _standing_instructions(user_id: str, message: str) -> str:
    """Standing guidance for every review: the user's own practice profile
    (generated for THEIR practice area, edited by them — never baked in) plus
    the firm playbook; the message's framing stacks on top."""
    user_settings = load_user_settings(user_id)
    playbook = (user_settings.contract_playbook or "").strip()
    practice_profile = (user_settings.practice_profile or "").strip()
    if practice_profile:
        practice_profile = (
            f"THE USER'S PRACTICE PROFILE ({user_settings.practice_area or 'their practice'}):\n"
            + practice_profile
        )
    return "\n\n".join(part for part in (practice_profile, playbook, message) if part)


async def _resolve_references(ids: list[str] | None, user_id: str) -> list[tuple[str, str]]:
    """Attached knowledge-base documents as (label, full text) — never truncated here."""
    references: list[tuple[str, str]] = []
    for ref_id in dict.fromkeys(ids or []):
        try:
            text = await contract_analysis_service.resolve_document_text(ref_id, user_id)
            label = await contract_analysis_service.document_label(ref_id, user_id)
            references.append((label, text))
        except LookupError:
            logger.warning("Draft reference document not found: %s", ref_id)
    return references


async def _job_progress(message: str, fraction: float) -> None:
    job_manager.report_progress(message, fraction)


@router.post("/chat")
async def contract_chat(
    request: ContractChatRequest,
    http_request: Request,
    current_user: TokenData = require_permission("contracts.use"),
):
    """Natural-language contract review.

    The message is routed by intent: a full-review ask submits the analysis
    pipeline as a background job (202 + job to poll, same result shape as
    /analyze); anything else is answered directly with quote-verified,
    highlightable citations into the contract text.
    """
    if request.document_id:
        try:
            text = await contract_analysis_service.resolve_document_text(
                request.document_id, current_user.user_id
            )
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
    elif request.draft_text:
        # The drafting workspace's current draft IS the document under
        # discussion — questions answer over it, draft mode revises it.
        text = request.draft_text
    elif request.mode == "draft":
        # Drafting from scratch — no reference document.
        text = ""
    else:
        raise HTTPException(
            status_code=400,
            detail="Select a contract first — only drafting works without one.",
        )

    client, user_keys = _llm_client(http_request, current_user.user_id)

    if request.mode in ("ask", "analyze", "redline", "draft"):
        # Explicit mode: the user chose the tool and their message is the
        # instruction set. Nothing is inferred.
        route = {"intent": request.mode, "instructions": request.message}
    else:
        route = await route_contract_message(client, request.message)
    user_id = current_user.user_id

    playbook = (load_user_settings(user_id).contract_playbook or "").strip()
    combined_instructions = _standing_instructions(
        user_id, route["instructions"] or request.message
    )

    # Redlining without a stated goal would mean the machine deciding what the
    # user wants. If neither the message nor the firm playbook gives direction,
    # ask — one question, quick-answer options — before touching the contract.
    if (
        request.mode is None
        and route["intent"] == "redline"
        and not route["instructions"]
        and not playbook
    ):
        return {
            "type": "clarify",
            "question": (
                "Before I redline — what's the goal? Redlines drafted for a "
                "negotiation look very different from a general risk cleanup."
            ),
            "options": [
                "We're negotiating — I represent the customer/client side",
                "We're negotiating — I represent the vendor/provider side",
                "Flag and fix anything risky or off-market, neutral review",
                "Tighten every clause as far as possible in my favor",
            ],
        }

    if route["intent"] in ("analyze", "redline"):
        wants_redlines = route["intent"] == "redline"

        async def do_analysis():
            result = await contract_analysis_service.analyze(
                text=text,
                contract_type="auto",
                user_id=user_id,
                document_id=request.document_id,
                user_keys=user_keys,
                instructions=combined_instructions,
            )
            if wants_redlines:
                edits = await generate_redlines(
                    client,
                    text,
                    result.get("issues") or [],
                    instructions=combined_instructions,
                )
                result["redlines"] = edits
                result["kind"] = "redlines"
                await contract_analysis_service.persist_redlines(
                    result["analysis_id"], edits, len(text)
                )
            return result

        job_id = await job_manager.submit(
            do_analysis,
            user_id=user_id,
            endpoint="/contract-analysis/chat",
            retry_policy=RETRY_POLICIES["ai_analysis"],
        )
        return JSONResponse(
            status_code=202,
            content={
                "type": "redline_started" if wants_redlines else "analysis_started",
                "job_id": job_id,
                "poll_url": f"/api/v1/jobs/{job_id}",
            },
        )

    if route["intent"] == "draft":
        # Attached reference documents are the draft's source material
        # ("a demand letter based on this service agreement"). They stack with
        # the selected contract, if any.
        references = await _resolve_references(request.reference_document_ids, user_id)
        if text and not request.draft_text:
            references.insert(0, ("Selected contract", text))
        reference_combined = (
            "\n\n".join(f"=== {label} ===\n{body}" for label, body in references) or None
        )

        async def do_draft():
            if request.draft_text:
                # Workspace iteration: revise the current draft — section by
                # section once it is long enough that re-sending the whole
                # document would be wasteful or would not fit.
                revised = await revise_draft(
                    client,
                    draft_text=request.draft_text,
                    instructions=combined_instructions,
                    progress=_job_progress,
                )
                # A scoped revision has no new title; "" tells the UI to keep its own.
                return {"kind": "draft", **revised, "title": revised.get("title") or ""}
            draft = await draft_document(
                client, instructions=combined_instructions, reference_text=reference_combined
            )
            return {"kind": "draft", **draft}

        job_id = await job_manager.submit(
            do_draft,
            user_id=user_id,
            endpoint="/contract-analysis/chat",
            retry_policy=RETRY_POLICIES["ai_analysis"],
        )
        return JSONResponse(
            status_code=202,
            content={
                "type": "draft_started",
                "job_id": job_id,
                "poll_url": f"/api/v1/jobs/{job_id}",
            },
        )

    try:
        result = await answer_contract_question(client, text, request.message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise handle_service_error(e, "Answer failed", logger)
    return {"type": "answer", **result}


@router.post("/draft/plan")
async def plan_long_draft(
    request: DraftPlanRequest,
    http_request: Request,
    current_user: TokenData = require_permission("contracts.use"),
):
    """Long drafts, phase 1: the section plan.

    One call over the FULL reference bundle (never truncated to a fixed size)
    produces the outline, a brief per section including what each section
    must leave to others, the shared definitions and a style guide. The user
    reviews and edits it before anything is written.
    """
    client, _ = _llm_client(http_request, current_user.user_id)
    user_id = current_user.user_id
    instructions = _standing_instructions(user_id, request.message)
    references = await _resolve_references(request.reference_document_ids, user_id)
    target_pages = request.target_pages

    async def do_plan():
        plan = await plan_document(
            client,
            instructions=instructions,
            references=references,
            target_pages=target_pages,
            progress=_job_progress,
        )
        return {"kind": "draft_plan", "plan": plan, "target_pages": target_pages}

    job_id = await job_manager.submit(
        do_plan,
        user_id=user_id,
        endpoint="/contract-analysis/draft/plan",
        retry_policy=RETRY_POLICIES["ai_analysis"],
    )
    return JSONResponse(
        status_code=202,
        content={
            "type": "draft_plan_started",
            "job_id": job_id,
            "poll_url": f"/api/v1/jobs/{job_id}",
        },
    )


@router.post("/draft/generate")
async def generate_long_draft(
    request: DraftGenerateRequest,
    http_request: Request,
    current_user: TokenData = require_permission("contracts.use"),
):
    """Long drafts, phases 2-3: every section in its own context window, in
    parallel, each with the full references and the whole plan; then one
    reconcile pass over the assembled document.
    """
    client, _ = _llm_client(http_request, current_user.user_id)
    user_id = current_user.user_id
    try:
        plan = normalize_plan(request.plan)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    instructions = _standing_instructions(user_id, request.message)
    references = await _resolve_references(request.reference_document_ids, user_id)

    async def do_generate():
        result = await generate_from_plan(
            client,
            plan=plan,
            instructions=instructions,
            references=references,
            progress=_job_progress,
        )
        return {"kind": "draft", **result}

    # Sections already retry individually; re-running a whole 30-page draft
    # on a late failure would multiply the cost for nothing.
    job_id = await job_manager.submit(
        do_generate,
        user_id=user_id,
        endpoint="/contract-analysis/draft/generate",
        retry_policy=RetryPolicy(max_retries=0),
    )
    return JSONResponse(
        status_code=202,
        content={
            "type": "draft_started",
            "job_id": job_id,
            "poll_url": f"/api/v1/jobs/{job_id}",
        },
    )


@router.get("/analyses")
async def list_analyses(
    limit: int = Query(50, ge=1, le=200),
    current_user: TokenData = require_permission("contracts.use"),
    db: AsyncSession = Depends(get_db),
    accessible_matters: set[str] = Depends(accessible_matter_ids),
):
    """List the caller's contract analyses (own + shared matters), newest first."""
    scope = ContractAnalysisRun.user_id == current_user.user_id
    if accessible_matters:
        scope = or_(scope, ContractAnalysisRun.matter_id.in_(list(accessible_matters)))
    runs = (
        (
            await db.execute(
                select(ContractAnalysisRun)
                .where(scope)
                .order_by(ContractAnalysisRun.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {
        "analyses": [
            {
                "analysis_id": r.id,
                "document_id": r.document_id,
                "contract_type": r.contract_type,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "issues": len((r.summary or {}).get("issues") or []),
            }
            for r in runs
        ]
    }


@router.get("/analyses/{analysis_id}")
async def get_full_analysis(
    analysis_id: str,
    http_request: Request,
    current_user: TokenData = require_permission("contracts.use"),
    db: AsyncSession = Depends(get_db),
    accessible_matters: set[str] = Depends(accessible_matter_ids),
):
    run = (
        await db.execute(select(ContractAnalysisRun).where(ContractAnalysisRun.id == analysis_id))
    ).scalar_one_or_none()
    if not run or not _run_accessible(run, current_user.user_id, accessible_matters):
        # Owner or a member of the run's matter; a null-owner run is nobody's.
        raise HTTPException(status_code=404, detail="Analysis not found")
    await _audit(
        http_request,
        current_user,
        AuditEventType.DATA_ACCESS,
        "contract_analysis_view",
        analysis_id,
        document_id=run.document_id,
    )

    parties = (
        (await db.execute(select(ContractParty).where(ContractParty.analysis_id == analysis_id)))
        .scalars()
        .all()
    )
    obligations = (
        (
            await db.execute(
                select(ContractObligation).where(ContractObligation.analysis_id == analysis_id)
            )
        )
        .scalars()
        .all()
    )
    deadlines = (
        (
            await db.execute(
                select(ContractDeadline).where(ContractDeadline.analysis_id == analysis_id)
            )
        )
        .scalars()
        .all()
    )
    defined = (
        (
            await db.execute(
                select(ContractDefinedTerm).where(ContractDefinedTerm.analysis_id == analysis_id)
            )
        )
        .scalars()
        .all()
    )

    summary = run.summary or {}
    return {
        "analysis_id": run.id,
        "contract_type": run.contract_type,
        "jurisdiction": run.jurisdiction,
        "summary": summary,
        "representing": summary.get("representing"),
        "posture": summary.get("posture"),
        "issues": summary.get("issues") or [],
        "executive_summary": summary.get("executive_summary"),
        "key_terms": summary.get("key_terms") or {},
        "parties": [
            {
                "id": p.id,
                "canonical_name": p.canonical_name,
                "role": p.role,
                "aliases": p.aliases,
                "detection_method": p.detection_method,
                "confidence": p.confidence,
                "first_span_start": p.first_span_start,
                "first_span_end": p.first_span_end,
            }
            for p in parties
        ],
        "obligations": [
            {
                "id": o.id,
                "subject_party": o.subject_party,
                "modal": o.modal,
                "action": o.action,
                "object_text": o.object_text,
                "conditions": o.conditions or [],
                "category": o.category,
                "is_unilateral": bool(o.is_unilateral),
                "is_perpetual": bool(o.is_perpetual),
                "is_continuing": bool(o.is_continuing),
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
                "defined": bool(t.defined),
                "usage_count": t.usage_count,
                "used_but_undefined": bool(t.used_but_undefined),
                "defined_but_unused": bool(t.defined_but_unused),
                "circular_reference": bool(t.circular_reference),
            }
            for t in defined
        ],
    }


@router.delete("/analyses/{analysis_id}")
async def delete_analysis(
    analysis_id: str,
    http_request: Request,
    current_user: TokenData = require_permission("contracts.use"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a stored analysis and everything derived from it. Owner only.

    An analysis holds verbatim contract text (issues, quotes, parties,
    obligations, redlines), so its owner must be able to remove it. Uniform
    404 for runs the caller does not own.
    """
    run = (
        await db.execute(select(ContractAnalysisRun).where(ContractAnalysisRun.id == analysis_id))
    ).scalar_one_or_none()
    if not run or not run.user_id or run.user_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Analysis not found")

    document_id = run.document_id
    # The child tables have no FK cascade to the run — delete them explicitly.
    for child in (
        ContractParty,
        ContractObligation,
        ContractDeadline,
        ContractDefinedTerm,
        ClauseDeviationFinding,
        ClauseTagFinding,
    ):
        await db.execute(delete(child).where(child.analysis_id == analysis_id))
    await db.delete(run)
    await db.commit()

    await _audit(
        http_request,
        current_user,
        AuditEventType.DATA_DELETION,
        "contract_analysis_deleted",
        analysis_id,
        document_id=document_id,
    )
    return {"status": "deleted", "id": analysis_id}


_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/analyses/{analysis_id}/export")
async def export_analysis(
    analysis_id: str,
    http_request: Request,
    format: str = Query("md", description='"md" or "docx"'),
    current_user: TokenData = require_permission("contracts.use"),
    db: AsyncSession = Depends(get_db),
    accessible_matters: set[str] = Depends(accessible_matter_ids),
):
    """Export a stored analysis as a downloadable report (Markdown or DOCX)."""
    fmt = (format or "").strip().lower()
    if fmt not in ("md", "docx"):
        raise HTTPException(status_code=400, detail='Invalid format — use "md" or "docx".')

    run = (
        await db.execute(select(ContractAnalysisRun).where(ContractAnalysisRun.id == analysis_id))
    ).scalar_one_or_none()
    if not run or not _run_accessible(run, current_user.user_id, accessible_matters):
        # Owner or a member of the run's matter; a null-owner run is nobody's.
        raise HTTPException(status_code=404, detail="Analysis not found")

    parties = (
        (await db.execute(select(ContractParty).where(ContractParty.analysis_id == analysis_id)))
        .scalars()
        .all()
    )
    obligations = (
        (
            await db.execute(
                select(ContractObligation).where(ContractObligation.analysis_id == analysis_id)
            )
        )
        .scalars()
        .all()
    )
    deadlines = (
        (
            await db.execute(
                select(ContractDeadline).where(ContractDeadline.analysis_id == analysis_id)
            )
        )
        .scalars()
        .all()
    )
    summary = run.summary or {}
    data = {
        "analysis_id": run.id,
        "contract_type": run.contract_type,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "representing": summary.get("representing"),
        "posture": summary.get("posture"),
        "executive_summary": summary.get("executive_summary"),
        "key_terms": summary.get("key_terms") or {},
        "issues": summary.get("issues") or [],
        "parties": [
            {"canonical_name": p.canonical_name, "role": p.role, "aliases": p.aliases}
            for p in parties
        ],
        "obligations": [
            {
                "subject_party": o.subject_party,
                "modal": o.modal,
                "action": o.action,
                "object_text": o.object_text,
                "deadlines": o.deadlines or [],
            }
            for o in obligations
        ],
        "deadlines": [
            {
                "description": d.description,
                "matched_text": d.matched_text,
                "resolved_date": d.resolved_date.isoformat() if d.resolved_date else None,
            }
            for d in deadlines
        ],
    }

    await _audit(
        http_request,
        current_user,
        AuditEventType.DATA_EXPORT,
        "contract_analysis_export",
        analysis_id,
        format=fmt,
        document_id=run.document_id,
    )

    filename = f"contract-analysis-{run.id[:8]}"
    if fmt == "md":
        return Response(
            content=render_markdown(data),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}.md"'},
        )

    payload = render_docx(data)
    return StreamingResponse(
        io.BytesIO(payload),
        media_type=_DOCX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}.docx"'},
    )


@router.post("/practice-profile")
async def generate_practice_profile(
    request: PracticeProfileRequest,
    http_request: Request,
    current_user: TokenData = require_permission("contracts.use"),
):
    """Generate a practice profile from the user's stated practice area.

    Nothing about any practice is baked into the product — the user says what
    they practice, this drafts a profile of what matters in that practice, and
    the user edits and owns it (saved via Settings). It then rides along with
    every review, redline, and draft as standing context.
    """
    from app.services.llm_clients import openai_chat, utility_model

    user_keys = UserAPIKeys.from_request(http_request, user_id=current_user.user_id)
    client = make_openai(
        user_keys.openai if user_keys and user_keys.openai else settings.openai_api_key,
        async_=True,
    )
    if client is None:
        raise HTTPException(
            status_code=400,
            detail="An OpenAI API key or a custom LLM endpoint is required. "
            "Configure one in Settings.",
        )

    prompt = (
        "An attorney practicing in this area is configuring their document-review "
        f"assistant: {request.practice_area.strip()}\n\n"
        "Write their PRACTICE PROFILE: a concise, practical brief (300-500 words) the "
        "assistant will read before every contract/document review, redline, and draft "
        "in this practice. Cover: the document types they most often handle; the clause "
        "types, terms, and provisions that matter most in this practice; the recurring "
        "red flags and traps; the deadlines/notice requirements typical of the area; and "
        "what a careful attorney in this practice always checks. Plain prose and short "
        "bullet lists. Write it FOR this specific practice area — no generic commercial "
        "contract boilerplate."
    )
    try:
        resp = await openai_chat(
            client,
            model=utility_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        profile = (resp.choices[0].message.content or "").strip()
    except Exception as e:  # surfaced as one clean error
        logger.warning("practice profile generation failed: %s", e)
        raise HTTPException(status_code=500, detail="Profile generation failed. Try again.")
    if not profile:
        raise HTTPException(status_code=500, detail="Profile generation returned nothing.")
    return {"practice_area": request.practice_area.strip(), "profile": profile}


@router.post("/compare")
async def compare_documents(
    request: CompareRequest,
    http_request: Request,
    current_user: TokenData = require_permission("contracts.use"),
):
    """Clause-by-clause comparison of 2-4 indexed contracts (202 + job).

    With more than two documents, the first is the baseline and every other
    document is compared against it — one job, one result set.
    """
    user_id = current_user.user_id

    doc_ids = request.document_ids or (
        [request.document_id_a, request.document_id_b]
        if request.document_id_a and request.document_id_b
        else None
    )
    if not doc_ids or len(doc_ids) < 2:
        raise HTTPException(status_code=400, detail="Provide 2-4 document ids to compare.")
    # De-dupe while preserving order; the baseline is the first id.
    doc_ids = list(dict.fromkeys(doc_ids))[:4]
    if len(doc_ids) < 2:
        raise HTTPException(status_code=400, detail="Provide at least two DIFFERENT documents.")

    texts: list[str] = []
    labels: list[str] = []
    try:
        for doc_id in doc_ids:
            texts.append(await contract_analysis_service.resolve_document_text(doc_id, user_id))
            labels.append(await contract_analysis_service.document_label(doc_id, user_id))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    user_keys = UserAPIKeys.from_request(http_request, user_id=user_id)
    client = make_openai(
        user_keys.openai if user_keys and user_keys.openai else settings.openai_api_key,
        async_=True,
    )
    if client is None:
        raise HTTPException(
            status_code=400,
            detail="An OpenAI API key or a custom LLM endpoint is required. "
            "Configure one in Settings.",
        )

    async def do_compare():
        comparisons = []
        for i in range(1, len(doc_ids)):
            result = await compare_contracts(
                client,
                texts[0],
                texts[i],
                label_a=labels[0],
                label_b=labels[i],
                focus=request.focus,
            )
            # Document ids ride along so the UI can open the texts side by side.
            comparisons.append(
                {
                    "kind": "comparison",
                    **result,
                    "document_id_a": doc_ids[0],
                    "document_id_b": doc_ids[i],
                    "focus": request.focus,
                }
            )
        if len(comparisons) == 1:
            return comparisons[0]
        return {"kind": "comparison_set", "comparisons": comparisons, "focus": request.focus}

    job_id = await job_manager.submit(
        do_compare,
        user_id=user_id,
        endpoint="/contract-analysis/compare",
        retry_policy=RETRY_POLICIES["ai_analysis"],
    )
    await _audit(
        http_request,
        current_user,
        AuditEventType.DATA_ACCESS,
        "contract_compare_submit",
        job_id=job_id,
        document_ids=doc_ids,
    )
    return JSONResponse(
        status_code=202,
        content={"type": "compare_started", "job_id": job_id, "poll_url": f"/api/v1/jobs/{job_id}"},
    )


@router.post("/draft-export")
async def export_draft(
    request: DraftExportRequest,
    http_request: Request,
    current_user: TokenData = require_permission("contracts.use"),
):
    """Render a drafted document as a Word file."""
    payload = render_draft_docx(request.title, request.text)
    await _audit(
        http_request,
        current_user,
        AuditEventType.DATA_EXPORT,
        "contract_draft_export",
        chars=len(request.text),
    )
    ascii_title = request.title.encode("ascii", "ignore").decode()
    safe_name = "".join(c for c in ascii_title if c.isalnum() or c in " -_").strip()[:60] or "draft"
    return StreamingResponse(
        iter([payload]),
        media_type=_DOCX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.docx"'},
    )


@router.post("/analyses/{analysis_id}/redline-export")
async def export_redlines_post(
    analysis_id: str,
    request: RedlineExportRequest,
    http_request: Request,
    current_user: TokenData = require_permission("contracts.use"),
    db: AsyncSession = Depends(get_db),
):
    """Redline export with user overrides of proposed wording."""
    return await _export_redlines(
        analysis_id,
        excluded={r.strip() for r in request.exclude if r.strip()},
        overrides=request.overrides,
        current_user=current_user,
        db=db,
        http_request=http_request,
    )


@router.get("/analyses/{analysis_id}/redline-export")
async def export_redlines(
    analysis_id: str,
    http_request: Request,
    exclude: str = Query(
        "", description="Comma-separated issue refs to leave out", max_length=20_000
    ),
    current_user: TokenData = require_permission("contracts.use"),
    db: AsyncSession = Depends(get_db),
):
    """Export stored redlines as a Word document with genuine tracked changes."""
    return await _export_redlines(
        analysis_id,
        excluded={ref.strip() for ref in exclude.split(",") if ref.strip()},
        overrides={},
        current_user=current_user,
        db=db,
        http_request=http_request,
    )


async def _export_redlines(
    analysis_id: str,
    *,
    excluded: set[str],
    overrides: dict[str, str],
    current_user: TokenData,
    db: AsyncSession,
    http_request: Request,
):
    run = (
        await db.execute(select(ContractAnalysisRun).where(ContractAnalysisRun.id == analysis_id))
    ).scalar_one_or_none()
    if not run or run.user_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Analysis not found")

    summary = run.summary or {}
    edits = summary.get("redlines") or []
    if not edits:
        raise HTTPException(status_code=404, detail="No redlines stored for this analysis.")
    if not run.document_id:
        raise HTTPException(
            status_code=409,
            detail="Redline export needs the original indexed document; this analysis "
            "was run on pasted text.",
        )
    kept = [e for e in edits if e.get("ref") not in excluded]
    # Apply the user's own wording where they edited a proposed change.
    if overrides:
        kept = [
            (
                {**e, "proposed_text": overrides[e["ref"]]}
                if e.get("ref") in overrides and overrides[e["ref"]].strip()
                else e
            )
            for e in kept
        ]

    # Render from the text extracted from the STORED ORIGINAL file, never from
    # the vector-chunk reconstruction the analysis ran on: chunk seams repeat
    # text, and a tracked-changes document that goes to opposing counsel must
    # contain the contract exactly as it was uploaded. The stored edits carry
    # offsets into the analysis text, so they are re-anchored by their verbatim
    # original text; any that cannot be anchored are listed in the export
    # rather than placed by guesswork.
    source = await _stored_original_text(run.document_id, current_user.user_id)
    if source is not None:
        text = source
        located, omitted = relocate_edits(text, kept)
    else:
        try:
            text = await contract_analysis_service.resolve_document_text(
                run.document_id, current_user.user_id
            )
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        if summary.get("redline_text_len") not in (None, len(text)):
            raise HTTPException(
                status_code=409,
                detail="The document was re-indexed since these redlines were generated — "
                "run the redline again.",
            )
        located, omitted = kept, []
        logger.warning(
            "redline export for %s fell back to indexed-chunk text (original file unavailable)",
            analysis_id,
        )

    payload = render_redline_docx(text, located, omitted=omitted)
    # Fidelity gate: the plain + deleted text of the rendered document must be
    # the source text, character for character. A renderer bug fails loudly
    # here instead of shipping a silently altered contract.
    if reconstruct_original_text(payload, text.count("\n") + 1) != text:
        logger.error("redline export for %s failed the fidelity check", analysis_id)
        raise HTTPException(
            status_code=500,
            detail="Redline export failed an integrity check and was not produced.",
        )
    await _audit(
        http_request,
        current_user,
        AuditEventType.DATA_EXPORT,
        "contract_redline_export",
        analysis_id,
        document_id=run.document_id,
        rendered=len(located),
        omitted=len(omitted),
    )
    return StreamingResponse(
        iter([payload]),
        media_type=_DOCX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="redline-{analysis_id[:8]}.docx"',
            "X-Redlines-Rendered": str(len(located)),
            "X-Redlines-Omitted": str(len(omitted)),
        },
    )


async def _stored_original_text(document_id: str, user_id: str) -> str | None:
    """Text extracted from the stored original file, or None if unavailable."""
    try:
        found = await document_service.get_document_text(document_id, user_id)
    except Exception as e:  # extraction failure falls back to chunk text
        logger.warning("original-file extraction failed for %s: %s", document_id, e)
        return None
    if not found:
        return None
    _, text = found
    text = text.strip()
    return text or None
