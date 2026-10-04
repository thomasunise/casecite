"""
Authority Mapper router.

Maps an uploaded document's legal propositions to verbatim-verified case-law
authorities. Analysis runs as a background job (it fans out to CourtListener and
the user's corpus plus several LLM calls); the client polls /jobs/{job_id} and
then fetches the stored result.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.authority_map import AuthorityMapping, AuthorityMapRun
from app.routers._matter_deps import accessible_matter_ids
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData
from app.services.authority_mapper import authority_mapper_service
from app.services.job_queue import job_manager
from app.services.permissions import require_permission
from app.services.user_keys import UserAPIKeys
from app.utils.ip_resolution import get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/authority-map", tags=["authority-map"])


class AuthorityMapRequest(BaseModel):
    document_text: str = Field(
        ..., description="Full text of the document to map", max_length=2_000_000
    )
    document_name: str | None = Field(None, max_length=500)
    document_id: str | None = Field(None, max_length=64)
    jurisdiction: str | None = Field(None, max_length=100)


@router.post("/analyze")
async def analyze_authority_map(
    request: AuthorityMapRequest,
    http_request: Request,
    current_user: TokenData = require_permission("authority_map.use"),
):
    """Submit an authority-mapping job. Returns a job_id to poll via /jobs/{id}."""
    if not request.document_text.strip():
        raise HTTPException(status_code=400, detail="document_text is required")

    user_keys = UserAPIKeys.from_request(http_request, user_id=current_user.user_id)
    user_id = current_user.user_id

    async def _run():
        return await authority_mapper_service.analyze(
            text=request.document_text,
            document_name=request.document_name,
            document_id=request.document_id,
            jurisdiction=request.jurisdiction,
            user_id=user_id,
            user_keys=user_keys,
        )

    job_id = await job_manager.submit(_run, user_id=user_id, endpoint="authority_map")

    await audit_service.log_event(
        event_type=AuditEventType.DATA_ACCESS,
        user_id=user_id,
        user_email=current_user.email,
        ip_address=get_client_ip(http_request),
        details={"action": "authority_map_submit", "job_id": job_id},
    )
    return {"job_id": job_id}


@router.get("/{run_id}")
async def get_authority_map(
    run_id: str,
    http_request: Request,
    current_user: TokenData = require_permission("authority_map.use"),
    db: AsyncSession = Depends(get_db),
    accessible_matters: set[str] = Depends(accessible_matter_ids),
):
    """Fetch a completed authority-mapping run with all verified mappings."""
    run = (
        await db.execute(select(AuthorityMapRun).where(AuthorityMapRun.id == run_id))
    ).scalar_one_or_none()
    # Owner or a member of the run's matter. Uniform 404 (no 403) so the endpoint
    # doesn't leak the existence of runs outside the caller's tenant.
    owner_ok = bool(run and run.user_id and run.user_id == current_user.user_id)
    member_ok = bool(
        run and accessible_matters and run.matter_id and run.matter_id in accessible_matters
    )
    if not run or not (owner_ok or member_ok):
        raise HTTPException(status_code=404, detail="Authority map not found")

    await audit_service.log_event(
        event_type=AuditEventType.DATA_ACCESS,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="authority_map",
        resource_id=run_id,
        ip_address=get_client_ip(http_request),
        details={"action": "authority_map_view"},
    )

    rows = (
        (await db.execute(select(AuthorityMapping).where(AuthorityMapping.run_id == run_id)))
        .scalars()
        .all()
    )
    return {
        "run_id": run.id,
        "document_name": run.document_name,
        "jurisdiction": run.jurisdiction,
        "summary": run.summary or {},
        "mappings": [
            {
                "id": m.id,
                "proposition": m.proposition,
                "doc_quote": m.doc_quote,
                "doc_span_start": m.doc_span_start,
                "doc_span_end": m.doc_span_end,
                "source": m.source,
                "case_name": m.case_name,
                "citation": m.citation,
                "source_ref": m.source_ref,
                "source_url": m.source_url,
                "support_quote": m.support_quote,
                "source_span_start": m.source_span_start,
                "source_span_end": m.source_span_end,
                "verified": bool(m.verified),
                "relevance": m.relevance,
                "note": m.note,
                "reasoning": m.reasoning,
            }
            for m in rows
        ],
    }


@router.delete("/{run_id}")
async def delete_authority_map(
    run_id: str,
    http_request: Request,
    current_user: TokenData = require_permission("authority_map.use"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete an authority-mapping run and its mappings. Owner only.

    The stored mappings carry verbatim quotes from the mapped document, so the
    owner must be able to remove them. Uniform 404 for runs the caller does not
    own (no existence leak).
    """
    run = (
        await db.execute(select(AuthorityMapRun).where(AuthorityMapRun.id == run_id))
    ).scalar_one_or_none()
    if not run or not run.user_id or run.user_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Authority map not found")

    # No FK cascade from mappings to their run — delete the children explicitly.
    await db.execute(delete(AuthorityMapping).where(AuthorityMapping.run_id == run_id))
    await db.delete(run)
    await db.commit()

    await audit_service.log_event(
        event_type=AuditEventType.DATA_DELETION,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="authority_map",
        resource_id=run_id,
        ip_address=get_client_ip(http_request),
        details={"action": "authority_map_deleted"},
    )
    return {"status": "deleted", "id": run_id}
