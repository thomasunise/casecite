import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import SQLAlchemyError

from app.models.schemas import ChatRequest, ChatResponse, ConversationExportRequest
from app.services import chat_sessions as chat_session_service
from app.services import conversation_export
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData
from app.services.authority_mapper import authority_mapper_service
from app.services.documents import document_service
from app.services.job_queue import RETRY_POLICIES, job_manager
from app.services.permissions import require_permission
from app.services.rag import rag_service
from app.services.rag.per_file import PER_FILE_MAX_FILES, per_file_answer
from app.services.rag.routing import route_query
from app.services.strategy import strategy_service
from app.services.user_keys import UserAPIKeys
from app.services.user_settings import load_user_settings
from app.utils.ip_resolution import get_client_ip

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# The exhaustive authority map fans out to CourtListener per proposition, per
# file — cap how many files one chat message can audit at once.
AUTHORITY_MAP_MAX_FILES = 8


@router.post("/export")
async def export_conversation(
    request: ConversationExportRequest,
    current_user: TokenData = require_permission("chat.use"),
) -> Response:
    """Render the transcript the client is showing as Word, PDF or Markdown.

    The transcript is supplied by the client because every chat page keeps its
    own message shape; nothing here re-runs retrieval or touches documents.
    """
    mime, ext = conversation_export.FORMATS[request.format]
    try:
        payload = conversation_export.render(
            request.format,
            request.title,
            [m.model_dump() for m in request.messages],
        )
    except conversation_export.PdfUnavailable as e:
        raise HTTPException(status_code=501, detail=str(e))
    filename = conversation_export.safe_filename(request.title, ext)
    return Response(
        content=payload,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request,
    current_user: TokenData = require_permission("chat.use"),
    async_mode: bool = Query(False, alias="async"),
) -> ChatResponse:
    """Send a message and get a RAG-powered response with case law integration. Requires authentication."""
    if rag_service is None:
        raise HTTPException(
            status_code=503,
            detail="RAG service is temporarily unavailable. Please try again later.",
        )

    # Eagerly capture context before potential background execution
    user_keys = UserAPIKeys.from_request(http_request, user_id=current_user.user_id)
    user_settings = load_user_settings(current_user.user_id)
    client_ip = get_client_ip(http_request)
    user_id = current_user.user_id
    user_email = current_user.email

    # Pre-resolve document IDs (requires await, must happen before returning 202)
    document_ids = None
    if request.document_filter and request.include_documents:
        if not request.document_filter.search_all:
            document_ids = await document_service.get_documents_by_filter(
                user_id=user_id,
                document_ids=request.document_filter.document_ids,
                folder_paths=request.document_filter.folder_paths,
                sources=request.document_filter.sources,
                doc_types=request.document_filter.doc_types,
                include_subfolders=request.document_filter.include_subfolders,
            )

    def _brief_citation(c: dict, idx: int) -> dict:
        # Map a strategy-brief citation into the full Citation model shape.
        conf = float(c.get("confidence") or 0)
        return {
            "id": c.get("id") or f"strat-{idx}",
            "source": c.get("source") or f"Source {idx + 1}",
            "type": c.get("type") or "document",
            "confidence": conf,
            "similarity": conf / 100 if conf > 1 else conf,
            "relevance_rank": idx + 1,
            "chunk_index": idx,
            "token_count": 0,
            "passage": c.get("passage") or "",
            # Strategy authorities carry the judge's one-line explanation of
            # how a lawyer would use them — surface it as the case summary.
            "case_summary": c.get("explanation"),
            "reasoning": [],
            "logic": {
                "query_intent": "",
                "matching_criteria": "Strategy brief coverage retrieval",
                "application": "",
            },
            "document_id": c.get("document_id"),
            "url": c.get("url"),
            "was_cited_by_ai": True,
        }

    async def do_work():
        logger.debug(f"Chat query from user {user_id}: {request.query[:100]}...")

        # Zero-controls composer: decide per message whether this is a grounded
        # question or a strategy ask, and whether authority would help. An
        # explicit include_case_law from the client always wins. The router
        # also distills the case-law SEARCH TERM — the raw message ("find me
        # case law for a dwi") is never a usable keyword query.
        intent, wants_authority, case_law_query, per_file = await route_query(
            request.query, user_keys
        )
        include_case_law = (
            request.include_case_law if request.include_case_law is not None else wants_authority
        )

        strategy_payload = None
        authority_map_job = None
        result = None
        if intent == "authority_map" and request.include_documents:
            # Exhaustive per-proposition audit ("give me ALL the case law for
            # this file / these files / this folder"): run the authority mapper
            # over the full text of every scoped file as a background job the
            # client polls via /jobs/{job_id}. Requires a limited scope — the
            # whole knowledge base is never audited in one pass.
            scoped_ids = list(document_ids or [])
            if not scoped_ids:
                content = (
                    "To map all supporting case law, first scope this chat to a "
                    "folder or specific files (pick them in the workspace or the "
                    "scope selector above the composer), then ask again."
                )
            elif len(scoped_ids) > AUTHORITY_MAP_MAX_FILES:
                content = (
                    f"That scope covers {len(scoped_ids)} files — the exhaustive "
                    f"authority map runs on up to {AUTHORITY_MAP_MAX_FILES} files "
                    "at a time. Narrow the selection and ask again."
                )
            else:
                docs_meta = []
                for doc_id in scoped_ids:
                    doc = await document_service.get_document(doc_id, user_id)
                    if doc:
                        docs_meta.append({"id": doc_id, "name": doc.filename})

                async def _map_all(ids=tuple(scoped_ids)):
                    files = []
                    for doc_id in ids:
                        loaded = await document_service.get_document_text(doc_id, user_id)
                        if not loaded:
                            continue
                        filename, text = loaded
                        if not text.strip():
                            continue
                        res = await authority_mapper_service.analyze(
                            text=text,
                            document_name=filename,
                            document_id=doc_id,
                            jurisdiction=None,
                            user_id=user_id,
                            user_keys=user_keys,
                        )
                        files.append({"document_id": doc_id, **res})
                    return {
                        "files": files,
                        "totals": {
                            "files": len(files),
                            "propositions": sum(f["summary"]["propositions"] for f in files),
                            "authorities": sum(f["summary"]["authorities"] for f in files),
                            "verified": sum(f["summary"]["verified"] for f in files),
                        },
                    }

                map_job_id = await job_manager.submit(
                    _map_all,
                    user_id=user_id,
                    endpoint="authority_map",
                    retry_policy=RETRY_POLICIES["ai_analysis"],
                )
                authority_map_job = {"job_id": map_job_id, "documents": docs_meta}
                names = ", ".join(d["name"] for d in docs_meta) or "the selected files"
                content = (
                    f"Mapping supporting case law across "
                    f"{len(docs_meta)} file{'s' if len(docs_meta) != 1 else ''} "
                    f"({names}) — reading each file in full, extracting every legal "
                    "proposition, and verifying authority for each one against the "
                    "real opinions."
                )
            result = {
                "content": content,
                "citations": [],
                "stats": {
                    "docs_searched": len(scoped_ids),
                    "chunks_retrieved": 0,
                    "processing_time": "",
                    "case_law_searched": 0,
                    "case_law_included": 0,
                    "query_intent": "authority_map",
                },
            }
        elif intent == "research":
            # Pure legal-research lookup ("find me case law on DWI"): outside
            # authority only. The user's documents are irrelevant here and
            # must not be dragged into the answer. Research questions get the
            # deep engine automatically — candidate opinions are read in full
            # and only quote-verified authorities are cited.
            result = await rag_service.generate_response(
                query=request.query,
                mode=request.mode,
                top_k=user_settings.top_k,
                similarity_threshold=user_settings.similarity_threshold,
                include_documents=False,
                include_case_law=(
                    request.include_case_law if request.include_case_law is not None else True
                ),
                case_law_limit=request.case_law_limit,
                case_law_query=case_law_query,
                deep_case_law=True,
                user_keys=user_keys,
                document_ids=None,
                user_id=user_id,
                rag_settings=user_settings,
            )
        # The strategy brief reads the documents by design — never route to it
        # when the client explicitly asked for a documents-off answer.
        elif intent == "strategy" and request.include_documents:
            try:
                folder_path = None
                brief_document_ids = None
                if request.document_filter and not request.document_filter.search_all:
                    folder_paths = request.document_filter.folder_paths or []
                    folder_path = folder_paths[0] if folder_paths else None
                    brief_document_ids = request.document_filter.document_ids
                brief = await strategy_service.generate_brief(
                    question=request.query,
                    folder_path=folder_path,
                    document_ids=brief_document_ids,
                    include_case_law=include_case_law,
                    user_id=user_id,
                    user_keys=user_keys,
                )
                strategy_payload = brief
                result = {
                    "content": brief.get("position") or "Strategy brief generated.",
                    "citations": [
                        _brief_citation(c, i) for i, c in enumerate(brief.get("citations") or [])
                    ],
                    "stats": {
                        "docs_searched": brief.get("scope", {}).get("documents_considered", 0),
                        "chunks_retrieved": len(brief.get("citations") or []),
                        "processing_time": "",
                        "case_law_searched": 0,
                        "case_law_included": sum(
                            1 for c in (brief.get("citations") or []) if c.get("type") == "case_law"
                        ),
                        "query_intent": "strategy",
                    },
                }
            except Exception as e:  # strategy routing must never kill chat
                logger.warning(f"Strategy routing failed, answering normally: {e}")
                strategy_payload = None
                result = None

        # Per-file map-reduce: the question is about the scoped files
        # individually/comparatively and the scope is a small multi-file set —
        # give every file its own context window, then synthesize. Any failure
        # falls back to the pooled RAG answer below.
        if (
            result is None
            and intent == "ask"
            and per_file
            and request.include_documents
            and document_ids
            and 2 <= len(document_ids) <= PER_FILE_MAX_FILES
        ):
            try:
                result = await per_file_answer(
                    query=request.query,
                    document_ids=document_ids,
                    user_id=user_id,
                    user_keys=user_keys,
                )
            except Exception as e:  # per-file must never kill chat
                logger.warning(f"Per-file answering failed, answering normally: {e}")
                result = None

        if result is None:
            result = await rag_service.generate_response(
                query=request.query,
                mode=request.mode,
                top_k=user_settings.top_k,
                similarity_threshold=user_settings.similarity_threshold,
                include_documents=request.include_documents,
                include_case_law=include_case_law,
                case_law_limit=request.case_law_limit,
                case_law_query=case_law_query,
                user_keys=user_keys,
                document_ids=document_ids,
                user_id=user_id,
                rag_settings=user_settings,
            )

        response_id = str(uuid.uuid4())

        await audit_service.log_event(
            event_type=AuditEventType.CHAT_QUERY,
            user_id=user_id,
            user_email=user_email,
            resource_type="chat",
            resource_id=response_id,
            ip_address=client_ip,
            details={
                "mode": request.mode.value if request.mode else "research",
                "include_documents": request.include_documents,
                "include_case_law": request.include_case_law,
                "query_length": len(request.query),
                "citations_count": len(result["citations"]),
            },
        )

        response_payload = ChatResponse(
            id=response_id,
            content=result["content"],
            citations=result["citations"] if request.include_citations else [],
            stats=result["stats"],
            mode=request.mode,
            timestamp=datetime.now(UTC),
            strategy=strategy_payload,
            authority_map_job=authority_map_job,
        ).model_dump(mode="json")

        # Persist the exchange to a chat session so conversations survive
        # reloads. Best-effort: storage problems must never fail the response.
        session_id = request.session_id
        try:
            if session_id is None:
                created = await chat_session_service.create_session(
                    user_id=user_id, title=request.query.strip()[:60]
                )
                session_id = created["id"]
            await chat_session_service.append_message(
                session_id, user_id, role="user", content=request.query
            )
            await chat_session_service.append_message(
                session_id,
                user_id,
                role="assistant",
                content=response_payload["content"],
                citations=response_payload["citations"],
                strategy=response_payload.get("strategy"),
                stats=response_payload["stats"],
            )
        except (
            LookupError,
            ValueError,
            KeyError,
            SQLAlchemyError,
            ConnectionError,
            TimeoutError,
            OSError,
            RuntimeError,
        ) as persist_err:
            logger.warning(f"Chat session persistence failed (non-fatal): {persist_err}")
            session_id = None
        response_payload["session_id"] = session_id

        return response_payload

    if async_mode:
        job_id = await job_manager.submit(
            do_work,
            user_id=user_id,
            endpoint="/chat",
            retry_policy=RETRY_POLICIES["ai_analysis"],
        )
        return JSONResponse(
            status_code=202,
            content={"job_id": job_id, "poll_url": f"/api/v1/jobs/{job_id}"},
        )

    # Synchronous mode — unchanged behaviour
    try:
        result_data = await do_work()
        return result_data
    except (ValueError, KeyError, ConnectionError, TimeoutError, OSError, RuntimeError) as e:
        logger.error(f"Chat error for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred processing your request. Please try again.",
        )
