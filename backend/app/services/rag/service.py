"""RAG Service - thin orchestrator that delegates to focused modules."""

import asyncio
import logging
import re
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional

from anthropic import AsyncAnthropic

from app.config import settings
from app.models.schemas import (
    AnalysisMode,
    ChatStats,
    QueryIntent,
    RAGSettings,
)
from app.services.case_law_research import research_authorities
from app.services.embeddings import embedding_service
from app.services.rag.case_law_guard import redact_unverified_case_law
from app.services.rag.citation_reasoning import enrich_citations_with_reasoning
from app.services.rag.citations import (
    build_case_law_citations,
    build_document_citations,
    extract_cited_cases,
)
from app.services.rag.claim_grounding import ground_answer_claims
from app.services.rag.enhancements import (
    annotate_source_locations,
    compress_context_results,
    expand_query,
    merge_search_results,
    verify_document_citations,
)
from app.services.rag.generation import (
    build_context_with_case_law,
    call_llm,
    get_model_max_tokens,
)
from app.services.rag.intent import detect_query_intent
from app.services.rag.prompt_safety import UNTRUSTED_CONTENT_RULE
from app.services.rag.prompts import get_default_grounding_rules, get_system_prompt
from app.services.rag.search import (
    SearchUnavailableError,
    get_document_chunks_directly,
    search_case_law,
    search_documents,
)
from app.services.vectordb import get_vector_db

if TYPE_CHECKING:
    from app.services.user_keys import UserAPIKeys

logger = logging.getLogger(__name__)

# --- Prompt injection guard ---
# Only phrasings that are unambiguous injection attempts. Legal text is full of
# "act as attorney-in-fact", "the system: ...", "stop work ... begin" and the
# like, so anything a contract or brief might legitimately say stays out of
# this list. Third-party document text is not filtered at all \u2014 it is
# delimited instead (see app.services.rag.prompt_safety).
_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+(all\s+|any\s+)?(the\s+|your\s+)?(previous|above|prior|earlier|system)"
    r"\s+(instructions?|prompts?|rules?|directions?|context))"
    r"|(disregard\s+(all\s+|any\s+)?(the\s+|your\s+)?(previous|above|prior|earlier|system)"
    r"\s+(instructions?|prompts?|rules?|directions?|context))"
    r"|(forget\s+(all\s+|any\s+)?(the\s+|your\s+)?(previous|above|prior|earlier|system)"
    r"\s+(instructions?|prompts?|rules?|context))"
    r"|(override\s+(all\s+|any\s+)?(the\s+|your\s+)?(previous|above|prior|earlier|system)"
    r"\s+(instructions?|prompts?|rules?))"
    r"|(you\s+are\s+now\s+(a|an|in)\s)"
    r"|(new\s+instructions?\s*:)"
    r"|(```\s*(system|assistant))"
    r"|(\<\/?system\>)"
    r"|(\<\/?assistant\>)"
    r"|(\x00)"
    r"|([\u200b-\u200f\u2028-\u202f\u2060\ufeff])",
    re.IGNORECASE,
)


def _sanitize_prompt_input(text: str, max_length: int = 100_000) -> str:
    """Sanitize user-provided text before interpolation into LLM prompts.

    Applies to the USER'S query only. Retrieved chunks and other third-party
    text are wrapped with ``untrusted_block`` instead of being rewritten, so
    quote verification against the original still works.
    """
    if not text:
        return text
    text = text[:max_length]
    text = _INJECTION_PATTERNS.sub("[FILTERED]", text)
    text = re.sub(r"={3,}", "==", text)
    return text


def _enforce_hipaa_provider_check(model: str) -> None:
    """If HIPAA enforcement is enabled, verify the model's provider is approved."""
    if not settings.hipaa_enforcement_enabled:
        return
    if not settings.approved_ai_providers:
        raise ValueError(
            "HIPAA enforcement is enabled but no approved_ai_providers configured. "
            "Set APPROVED_AI_PROVIDERS to allow LLM usage."
        )
    provider = None
    model_lower = (model or "").lower()
    if "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
        provider = "openai"
    elif "claude" in model_lower:
        provider = "anthropic"
    elif "gemini" in model_lower:
        provider = "google"
    else:
        provider = "unknown"
    approved_lower = [p.lower() for p in settings.approved_ai_providers]
    if provider not in approved_lower:
        raise ValueError(
            f"HIPAA enforcement: AI provider '{provider}' (model '{model}') is not in "
            f"approved providers list: {settings.approved_ai_providers}"
        )


class RAGService:
    def __init__(self):
        self.vector_db = get_vector_db()
        # Both clients carry settings.api_timeout and bounded retries; the
        # OpenAI one goes through the shared factory so OPENAI_BASE_URL /
        # the admin endpoint override apply here too.
        from app.services.llm_clients import SDK_MAX_RETRIES, make_openai

        self.openai = (
            make_openai(settings.openai_api_key, async_=True) if settings.openai_api_key else None
        )
        self.anthropic = (
            AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                timeout=settings.api_timeout,
                max_retries=SDK_MAX_RETRIES,
            )
            if settings.anthropic_api_key
            else None
        )

    async def index_document(
        self,
        document_id: str,
        text: str,
        filename: str,
        source: str = "local",
        doc_type: str = "document",
        metadata: dict[str, Any] = None,
        user_keys: Optional["UserAPIKeys"] = None,
        folder_path: str = None,
        user_id: str = "",
        matter_id: str | None = None,
    ) -> int:
        """Index a document by chunking and embedding it."""
        if self.vector_db is None:
            raise RuntimeError("Vector database not available. Check DB configuration and logs.")
        chunks = embedding_service.chunk_text(text)
        if not chunks:
            return 0

        chunk_texts = [c["text"] for c in chunks]
        embeddings = await embedding_service.embed_texts(chunk_texts, user_keys=user_keys)

        if not folder_path and metadata:
            folder_path = (
                metadata.get("folder_path") or metadata.get("parent_folder") or f"/{source}/"
            )
        elif not folder_path:
            folder_path = f"/{source}/"

        # Sanitize folder_path to prevent directory traversal
        import posixpath

        folder_path = posixpath.normpath(folder_path)
        if ".." in folder_path.split("/"):
            logger.warning(f"Blocked directory traversal in folder_path: {folder_path}")
            folder_path = f"/{source}/"

        documents = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
            chunk_doc = {
                "id": f"{document_id}_{i}",
                "embedding": embedding,
                "text": chunk["text"],
                "document_id": document_id,
                "chunk_index": chunk["chunk_index"],
                "token_count": chunk["token_count"],
                "filename": filename,
                "source": source,
                "doc_type": doc_type,
                "folder_path": folder_path,
                "created_at": datetime.now(UTC).isoformat(),
                **(metadata or {}),
                # Trusted scope fields last so caller-supplied metadata can never
                # override the owner/matter that enforce tenant isolation.
                "user_id": user_id,
            }
            # Only tag matter_id when set — the vector store rejects None-valued
            # metadata, and an untagged chunk stays owner-scoped (by user_id).
            if matter_id:
                chunk_doc["matter_id"] = matter_id
            documents.append(chunk_doc)

        await self.vector_db.add_documents(documents)
        return len(documents)

    async def search(
        self,
        query: str,
        top_k: int = None,
        similarity_threshold: float = None,
        filter: dict | None = None,
        use_hybrid: bool = None,
        use_reranking: bool = None,
        user_keys: Optional["UserAPIKeys"] = None,
        document_ids: list[str] | None = None,
        user_id: str = "",
        matter_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for relevant documents. Delegates to search module."""
        return await search_documents(
            vector_db=self.vector_db,
            query=query,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            filter=filter,
            use_hybrid=use_hybrid,
            use_reranking=use_reranking,
            user_keys=user_keys,
            document_ids=document_ids,
            user_id=user_id,
            matter_ids=matter_ids,
        )

    async def generate_response(
        self,
        query: str,
        mode: AnalysisMode = AnalysisMode.RESEARCH,
        model: str = None,
        top_k: int = None,
        similarity_threshold: float = None,
        include_documents: bool = True,
        include_case_law: bool = True,
        case_law_limit: int = 5,
        case_law_query: str | None = None,
        deep_case_law: bool = False,
        user_keys: Optional["UserAPIKeys"] = None,
        document_ids: list[str] | None = None,
        user_id: str = "",
        rag_settings: Any | None = None,
    ) -> dict[str, Any]:
        """Generate a RAG response with citations from documents and case law."""
        start_time = time.time()

        # Get LLM clients - prefer user keys (BYOK), fall back to server keys
        openai_client = None
        anthropic_client = None
        gemini_model = None

        if user_keys:
            openai_client = user_keys.get_async_openai_client()
            anthropic_client = user_keys.get_async_anthropic_client()
            if user_keys.has_google():
                gemini_model = user_keys.get_google_model()

        if not openai_client:
            openai_client = self.openai
        if not anthropic_client:
            anthropic_client = self.anthropic

        # Resolve effective per-user settings up front so the model choice and
        # retrieval toggles apply to every code path below (including no-results).
        effective_settings = rag_settings if rag_settings else RAGSettings()
        model = model or effective_settings.llm_model or settings.openai_chat_model

        # Search for relevant documents. Infrastructure failures surface as an
        # honest "search is down" answer — never as "no relevant documents".
        try:
            search_results = await self._retrieve_documents(
                query=query,
                include_documents=include_documents,
                document_ids=document_ids,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                effective_settings=effective_settings,
                user_keys=user_keys,
                user_id=user_id,
                openai_client=openai_client,
                anthropic_client=anthropic_client,
                gemini_model=gemini_model,
                model=model,
            )
        except SearchUnavailableError as e:
            logger.error(f"[RAG] Search unavailable for user {user_id}: {e}")
            return {
                "content": (
                    f"⚠ I couldn't search your documents: {e}\n\n"
                    "No answer was attempted — this is an infrastructure problem, "
                    "not a gap in your documents."
                ),
                "citations": [],
                "stats": ChatStats(
                    docs_searched=0,
                    chunks_retrieved=0,
                    processing_time=f"{time.time() - start_time:.2f}s",
                    case_law_searched=0,
                    case_law_included=0,
                ),
            }

        # Search CourtListener for case law. The keyword term is the distilled
        # topic (never the raw message) and every hit is judged against the
        # question before it can be cited. Hard time budget: full-opinion
        # fetches are real network reads — an unlucky sequence of retries must
        # degrade to "no case law", never stall the whole chat request.
        case_law_results = []
        if include_case_law:
            # Research-intent chat gets the deep engine automatically: decompose
            # the question into doctrines, read candidate opinions IN FULL, and
            # keep only authorities whose quote verifies verbatim against the
            # opinion text. Falls back to the fast snippet search whenever the
            # deep pass yields nothing (no OpenAI client, timeout, all dropped)
            # so a research question is never answered worse than before.
            if deep_case_law and openai_client is not None:
                try:
                    deep_results, deep_status = await asyncio.wait_for(
                        research_authorities(
                            question=query,
                            search_query=case_law_query,
                            client=openai_client,
                            limit=case_law_limit,
                        ),
                        timeout=140.0,
                    )
                    case_law_results = deep_results
                    logger.info(f"Deep case-law research status: {deep_status}")
                except TimeoutError:
                    logger.warning(
                        "Deep case-law research exceeded its 140s budget; "
                        "falling back to snippet search"
                    )
                except Exception as e:  # deep pass must never kill chat
                    logger.warning(f"Deep case-law research failed, falling back: {e}")
            if not case_law_results:
                try:
                    case_law_results = await asyncio.wait_for(
                        search_case_law(
                            case_law_query or query,
                            limit=case_law_limit,
                            question=query,
                            user_keys=user_keys,
                        ),
                        timeout=60.0,
                    )
                except TimeoutError:
                    logger.warning("Case-law search exceeded its 60s budget; answering without it")

        # Threshold transparency: if document search came back empty, probe
        # once WITHOUT the similarity floor. If matches exist below the
        # threshold, say so with numbers — "no relevant documents" while the
        # threshold silently discards real matches is indistinguishable from
        # data loss to the user.
        if not search_results and not case_law_results and include_documents and not document_ids:
            effective_threshold = similarity_threshold or settings.similarity_threshold
            try:
                probe = await self.search(
                    query,
                    top_k=3,
                    similarity_threshold=0.001,
                    use_hybrid=False,
                    use_reranking=False,
                    user_keys=user_keys,
                    user_id=user_id,
                )
            except SearchUnavailableError:
                probe = []
            if probe:
                best = max(r.get("similarity", 0.0) for r in probe)
                best_file = (probe[0].get("metadata") or {}).get("filename", "a document")
                return {
                    "content": (
                        f"⚠ Your documents ARE indexed, but nothing cleared your "
                        f"similarity threshold. The closest match — in "
                        f"“{best_file}” — scored {best:.2f}, and your threshold "
                        f"of {effective_threshold:.2f} discarded it. Lower the "
                        f"Similarity Threshold in Settings → Retrieval "
                        f"(0.25 recommended) and ask again."
                    ),
                    "citations": [],
                    "stats": ChatStats(
                        docs_searched=0,
                        chunks_retrieved=0,
                        processing_time=f"{time.time() - start_time:.2f}s",
                        case_law_searched=0,
                        case_law_included=0,
                    ),
                }

        # If no RAG sources requested or found, generate direct LLM response
        if not search_results and not case_law_results:
            return await self._handle_no_results(
                query,
                mode,
                model,
                include_documents,
                include_case_law,
                openai_client,
                anthropic_client,
                gemini_model,
                start_time,
                effective_settings,
            )

        # Build context from both sources. Context compression trims each chunk to
        # its most query-relevant sentences so more documents fit the token budget;
        # citations below still use the full, uncompressed passages.
        context_results = (
            compress_context_results(search_results, query)
            if effective_settings.context_compression
            else search_results
        )
        context = build_context_with_case_law(context_results, case_law_results)
        self._log_debug_context(context_results, case_law_results, context)

        # Detect query intent
        if mode == AnalysisMode.STRATEGY:
            query_intent = QueryIntent.ANALYTICAL
            logger.debug("[RAG] Strategy mode selected - using ANALYTICAL intent")
        else:
            query_intent = detect_query_intent(query)
            logger.info(
                f"[RAG] Query intent detected: {query_intent.value} for query: '{query[:50]}...'"
            )

        # Get system prompt and build user prompt. The context below carries
        # third-party text in delimited blocks; the rule (once per prompt)
        # tells the model those blocks are data, not instructions.
        system_prompt = (
            get_system_prompt(mode, query_intent=query_intent, rag_settings=effective_settings)
            + "\n\n"
            + UNTRUSTED_CONTENT_RULE
        )
        user_prompt = self._build_user_prompt(
            query, context, query_intent, case_law_results, effective_settings
        )

        # Generate LLM response (model already resolved from user settings above)
        _enforce_hipaa_provider_check(model)
        # Honor the user's max-tokens setting, capped by what the model/intent allows.
        model_token_cap = get_model_max_tokens(model, query_intent)
        if query_intent == QueryIntent.FACTUAL:
            max_tokens = model_token_cap
        else:
            max_tokens = min(effective_settings.max_tokens, model_token_cap)

        try:
            content = await call_llm(
                openai_client,
                anthropic_client,
                gemini_model,
                model,
                system_prompt,
                user_prompt,
                max_tokens,
                effective_settings.temperature,
            )
        except ValueError:
            raise
        except (KeyError, ConnectionError, TimeoutError, OSError, RuntimeError) as e:
            logger.error(f"LLM generation failed: {e}", exc_info=True)
            raise ValueError(f"AI generation failed: {type(e).__name__}. Please try again.")

        # Case law is never trusted from the model: redact any case reference
        # not traceable to this request's CourtListener results or the user's
        # own retrieved passages.
        content, removed_refs = redact_unverified_case_law(
            content, case_law_results, search_results
        )
        if removed_refs:
            logger.warning(
                f"[CaseLawGuard] Removed {len(removed_refs)} unverified case "
                f"reference(s) from chat answer: {removed_refs}"
            )

        # Build citations
        cited_cases = extract_cited_cases(content, case_law_results) if case_law_results else []
        citations = build_document_citations(search_results, query, mode)
        # Citation verification: only keep `was_cited_by_ai` for citations whose
        # content is actually reflected in the answer (otherwise reset to PENDING).
        if effective_settings.citation_verification:
            verify_document_citations(citations, content)
        # Source tracking: record precise chunk/page/char location for each citation.
        if effective_settings.source_tracking:
            annotate_source_locations(citations, search_results)

        # Claim-level grounding: the answer's OWN claims become the document
        # citations — each with exact contract language verified verbatim and
        # pinned to a char span in its source file. Replaces chunk-provenance
        # citations whenever it succeeds; any failure keeps the chunk ones.
        grounded = None
        if include_documents and search_results:
            try:
                grounded = await ground_answer_claims(
                    query=query,
                    answer=content,
                    search_results=search_results,
                    user_id=user_id,
                    user_keys=user_keys,
                )
            except Exception as e:  # grounding is best-effort
                logger.warning(f"Claim grounding failed, keeping chunk citations: {e}")
        if grounded:
            citations = grounded

        case_law_citations = build_case_law_citations(
            case_law_results, cited_cases, len(search_results), query
        )
        citations.extend(case_law_citations)
        # Auditable per-citation reasoning (ONE utility-LLM call). Grounded
        # claim citations already carry their own Claim→Evidence chains, so the
        # pass then only needs to cover the case-law citations.
        await enrich_citations_with_reasoning(
            case_law_citations if grounded else citations,
            query=query,
            answer=content,
            user_keys=user_keys,
        )

        processing_time = time.time() - start_time

        # "Docs searched" = documents in THIS query's scope — the scoped file
        # count when a filter applies, else the user's indexed documents.
        # (Never the vector store's chunk count: one file = many chunks, and
        # the collection total spans every user.)
        if not include_documents:
            docs_searched = 0
        elif document_ids is not None:
            docs_searched = len(document_ids)
        else:
            # Lazy import: documents.py imports rag_service at module load.
            from app.services.documents import document_service

            docs_searched = 0
            if user_id:
                try:
                    doc_stats = await document_service.get_stats(user_id)
                    docs_searched = doc_stats.get("by_status", {}).get("indexed", 0)
                except (ValueError, KeyError, RuntimeError):
                    docs_searched = len(
                        {
                            (c.get("metadata") or {}).get("document_id")
                            for c in search_results
                            if (c.get("metadata") or {}).get("document_id")
                        }
                    )

        return {
            "content": content,
            "citations": citations,
            "stats": ChatStats(
                docs_searched=docs_searched,
                chunks_retrieved=len(search_results),
                processing_time=f"{processing_time:.2f}s",
                case_law_searched=len(case_law_results) if include_case_law else 0,
                case_law_included=len(cited_cases),
                query_intent=query_intent.value,
            ),
        }

    async def _retrieve_documents(
        self,
        *,
        query,
        include_documents,
        document_ids,
        top_k,
        similarity_threshold,
        effective_settings,
        user_keys,
        user_id,
        openai_client,
        anthropic_client,
        gemini_model,
        model,
    ) -> list[dict[str, Any]]:
        """Retrieve document chunks for the query (selected docs or semantic search).

        Raises SearchUnavailableError when the search infrastructure fails —
        the caller turns that into an honest error answer instead of "no
        relevant documents".
        """
        if not include_documents:
            return []

        if document_ids:
            logger.info(
                f"[RAG] DOCUMENT CHAT MODE: Loading content from {len(document_ids)} selected document(s)"
            )
            search_results = await get_document_chunks_directly(
                self.vector_db, document_ids, top_k or 15, user_id=user_id
            )
            logger.info(f"[RAG] Loaded {len(search_results)} chunks from selected documents")
            if not search_results:
                logger.warning(f"[RAG] No chunks found for document IDs: {document_ids}")
            return search_results

        # Query expansion: search the original query plus LLM-generated
        # paraphrases, then merge by best-similarity per chunk (multi-query).
        queries = [query]
        if effective_settings.query_expansion:
            queries = await expand_query(
                query, openai_client, anthropic_client, gemini_model, model
            )
            logger.info(f"[RAG] Query expansion -> {len(queries)} queries")

        result_lists = []
        for q in queries:
            result_lists.append(
                await self.search(
                    q,
                    top_k=top_k,
                    similarity_threshold=similarity_threshold,
                    use_hybrid=effective_settings.hybrid_search,
                    use_reranking=effective_settings.enable_reranking,
                    user_keys=user_keys,
                    document_ids=None,
                    user_id=user_id,
                )
            )
        return (
            merge_search_results(result_lists, top_k or settings.top_k)
            if len(result_lists) > 1
            else result_lists[0]
        )

    async def _handle_no_results(
        self,
        query,
        mode,
        model,
        include_documents,
        include_case_law,
        openai_client,
        anthropic_client,
        gemini_model,
        start_time,
        effective_settings=None,
    ) -> dict[str, Any]:
        """Handle case when no search results are found."""
        effective_settings = effective_settings or RAGSettings()
        if not include_documents and not include_case_law:
            # RAG was disabled intentionally, just use LLM directly
            drafting_keywords = [
                "draft",
                "generate a",
                "write a",
                "motion to",
                "complaint",
                "document drafter",
                "begin the document",
                "ready-to-file",
            ]
            is_drafting = any(kw in query.lower() for kw in drafting_keywords)

            system_prompt = get_system_prompt(mode, is_drafting=is_drafting)
            model = model or effective_settings.llm_model or settings.openai_chat_model
            # Respect the user's max-tokens setting, capped by the model ceiling.
            max_tokens = min(effective_settings.max_tokens, get_model_max_tokens(model))
            # Drafting needs a little more creativity; treat 0.3 as a floor there.
            temperature = (
                max(effective_settings.temperature, 0.3)
                if is_drafting
                else effective_settings.temperature
            )

            try:
                content = await call_llm(
                    openai_client,
                    anthropic_client,
                    gemini_model,
                    model,
                    system_prompt,
                    query,
                    max_tokens,
                    temperature,
                )
            except ValueError:
                raise
            except (KeyError, ConnectionError, TimeoutError, OSError, RuntimeError) as e:
                logger.error(f"LLM generation failed: {e}", exc_info=True)
                raise ValueError(f"AI generation failed: {type(e).__name__}. Please try again.")

            # Direct-LLM path has no retrieved sources at all, so no case
            # reference the model produces here can be verified — remove all.
            content, removed_refs = redact_unverified_case_law(content)
            if removed_refs:
                logger.warning(
                    f"[CaseLawGuard] Removed {len(removed_refs)} unverified case "
                    f"reference(s) from direct answer: {removed_refs}"
                )

            return {
                "content": content,
                "citations": [],
                "stats": ChatStats(
                    docs_searched=0,
                    chunks_retrieved=0,
                    processing_time=f"{time.time() - start_time:.2f}s",
                    case_law_searched=0,
                    case_law_included=0,
                ),
            }

        # RAG was enabled but nothing was found. An EMPTY index and "no match"
        # are different truths — never report an empty library as a bad query.
        content = (
            "I couldn't find any relevant documents in the knowledge base or "
            "case law for your query. Please try rephrasing or ensure relevant "
            "documents have been indexed."
        )
        if include_documents and self.vector_db is not None:
            try:
                db_stats = await self.vector_db.get_stats()
                if db_stats.get("total_chunks", 0) == 0:
                    content = (
                        "⚠ Your document search index is empty — there is nothing "
                        "to search yet. If you previously uploaded documents, the "
                        "index may have been reset; re-indexing runs automatically "
                        "at startup, or you can re-upload. Check each document's "
                        "status in the knowledge base."
                    )
            except (ValueError, KeyError, ConnectionError, TimeoutError, OSError, RuntimeError):
                pass  # stats are best-effort; fall through to the generic message
        return {
            "content": content,
            "citations": [],
            "stats": ChatStats(
                docs_searched=0,
                chunks_retrieved=0,
                processing_time=f"{time.time() - start_time:.2f}s",
                case_law_searched=0,
                case_law_included=0,
            ),
        }

    def _build_user_prompt(
        self, query, context, query_intent, case_law_results, effective_settings
    ) -> str:
        """Build the user prompt based on query intent."""
        if query_intent == QueryIntent.FACTUAL:
            return f"""Answer this question using the documents below:

Question: {_sanitize_prompt_input(query)}

=== DOCUMENTS ===
{context}
=== END ===

Answer directly and concisely. Reference the source document."""
        else:
            case_law_instruction = ""
            if case_law_results:
                case_law_instruction = """

IMPORTANT - Case Law Citation Rules:
- Only cite a case if it DIRECTLY supports or is relevant to your analysis
- Do NOT cite cases just because they were provided - only cite if genuinely applicable
- When you cite a case, use the full case name (e.g., "Smith v. Jones" or "In re Smith")
- If none of the provided cases are relevant to the specific question, do not cite any
- Quality over quantity - it's better to cite 1-2 highly relevant cases than 10 tangentially related ones
- NEVER cite a case from memory. Any case reference not present in the provided context is automatically removed from your answer before the user sees it"""
            else:
                case_law_instruction = """

IMPORTANT: No case-law context was retrieved for this message. Do NOT cite any case law, precedent, or reporter citations from memory — any such reference is automatically removed from your answer before the user sees it."""

            if effective_settings.custom_grounding_rules:
                grounding_rules = effective_settings.custom_grounding_rules
            else:
                grounding_rules = get_default_grounding_rules()

            return f"""Using the documents below as context, answer this query:

Query: {_sanitize_prompt_input(query)}

=== DOCUMENT CONTEXT ===
{context}
=== END OF CONTEXT ===
{case_law_instruction}

{grounding_rules}"""

    def _log_debug_context(self, search_results, case_law_results, context):
        """Log debug info about search results and context."""
        logger.debug(f"[RAG Debug] Document results: {len(search_results)}")
        for i, r in enumerate(search_results[:3]):
            logger.debug(
                f"  Doc {i + 1}: {r.get('metadata', {}).get('filename', 'Unknown')} (sim: {r.get('similarity', 0):.3f})"
            )
        logger.debug(f"[RAG Debug] Case law results: {len(case_law_results)}")
        for i, r in enumerate(case_law_results[:3]):
            logger.debug(f"  Case {i + 1}: {r.get('metadata', {}).get('case_name', 'Unknown')}")
        logger.debug(f"[RAG Debug] Context length: {len(context)} chars")

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and all its chunks from the index."""
        if self.vector_db is None:
            logger.warning(f"Vector DB unavailable, skipping vector deletion for {document_id}")
            return True
        return await self.vector_db.delete_by_document(document_id)
