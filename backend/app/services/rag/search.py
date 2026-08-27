"""Search pipeline for RAG - document search, direct chunk fetch, and case law search."""

import json
import logging
from typing import TYPE_CHECKING, Any, Optional

import httpx

from app.config import settings
from app.services.courtlistener import courtlistener_service
from app.services.embeddings import embedding_service
from app.services.llm_clients import make_openai, openai_chat, utility_model
from app.services.rag.prompt_safety import UNTRUSTED_CONTENT_RULE, untrusted_block
from app.services.resilience import CircuitBreakerOpen, retry_with_backoff
from app.services.search import search_service

if TYPE_CHECKING:
    from app.services.user_keys import UserAPIKeys

logger = logging.getLogger(__name__)


class SearchUnavailableError(RuntimeError):
    """Search infrastructure failed (embeddings down, key rejected).

    Results are UNKNOWN, not empty — callers must never present this as
    "no matching documents". Carries a user-actionable message.
    """


async def search_documents(
    vector_db,
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
    """
    Search for relevant documents with enterprise-grade features.

    Supports:
    - Boolean query parsing (AND, OR, NOT, phrases)
    - Hybrid search (semantic + keyword BM25)
    - Cross-encoder reranking for precision
    - Advanced filtering (date, court, type)
    - Document ID filtering for scoped searches
    - Tenant isolation via user_id
    """
    top_k = top_k or settings.top_k
    similarity_threshold = similarity_threshold or settings.similarity_threshold
    use_hybrid = use_hybrid if use_hybrid is not None else settings.hybrid_search_enabled
    use_reranking = use_reranking if use_reranking is not None else settings.rerank_enabled

    # When specific documents are selected, use a lower threshold floor
    if document_ids:
        original_threshold = similarity_threshold
        similarity_threshold = min(similarity_threshold, 0.3)
        logger.debug(
            f"[Search] Specific documents selected, threshold: {original_threshold} -> {similarity_threshold}"
        )

    # Parse the query for Boolean operators and filters
    parsed_query = search_service.parse_query(query)

    # Get the semantic query (without Boolean operators)
    semantic_query = parsed_query.get_semantic_query() or query

    # Generate query embedding with retry logic
    try:
        query_embedding = await retry_with_backoff(
            lambda q: embedding_service.embed_query(q, user_keys=user_keys),
            semantic_query,
            circuit_breaker_name="embeddings",
            max_attempts=3,
        )
    except CircuitBreakerOpen:
        logger.error("Embedding service circuit breaker open")
        raise SearchUnavailableError(
            "The embedding service is temporarily unavailable after repeated "
            "failures. Wait a minute and try again."
        )
    except Exception as e:  # every embed failure means "could not look"
        # An embedding failure means we could not LOOK, not that nothing was
        # found — swallowing this used to surface as "no relevant documents",
        # and provider SDK errors (openai.AuthenticationError etc.) used to
        # escape as raw 500s that leaked the upstream error payload.
        logger.error(f"Failed to generate query embedding: {e}")
        lowered = str(e).lower()
        if "api key" in lowered or "invalid_api_key" in lowered or "401" in lowered:
            reason = (
                "The embedding API key was rejected — check your key in Settings "
                "(and the server's OPENAI_API_KEY if you run the instance)."
            )
        else:
            reason = "Generating the search embedding failed. Check your API key in Settings and try again."
        raise SearchUnavailableError(reason) from e

    # Build filter - always enforce a tenant scope. The caller can see chunks
    # they own (user_id) OR chunks in a matter they belong to (matter_id in
    # matter_ids); combined as $or so a shared-matter document is visible to
    # every member while a user's own chunks stay visible regardless of matter
    # tagging (back-compat with chunks indexed before matter_id existed).
    where_conditions = []
    tenant_conditions = []
    if user_id:
        tenant_conditions.append({"user_id": user_id})
    if matter_ids:
        tenant_conditions.append({"matter_id": {"$in": list(matter_ids)}})
    if len(tenant_conditions) == 1:
        where_conditions.append(tenant_conditions[0])
    elif len(tenant_conditions) > 1:
        where_conditions.append({"$or": tenant_conditions})
    if document_ids:
        where_conditions.append({"document_id": {"$in": document_ids}})
        logger.debug(f"[Search] Filtering to documents: {document_ids}")
    if filter:
        for k, v in filter.items():
            where_conditions.append({k: v})

    if len(where_conditions) > 1:
        search_filter = {"$and": where_conditions}
    elif len(where_conditions) == 1:
        search_filter = where_conditions[0]
    else:
        search_filter = None

    # Initial vector DB search - retrieve more if reranking
    initial_top_k = settings.rerank_top_k if use_reranking else top_k

    results = await vector_db.search(
        query_embedding=query_embedding,
        top_k=initial_top_k,
        filter=search_filter,
    )

    logger.debug(f"[Search] Vector DB returned {len(results)} results before threshold filter")

    # Filter by similarity threshold
    filtered_results = [r for r in results if r["similarity"] >= similarity_threshold]
    logger.debug(
        f"[Search] After threshold filter ({similarity_threshold}): {len(filtered_results)} results"
    )
    if results and not filtered_results:
        # Best-effort fallback: an absolute cosine floor is a junk filter for
        # large corpora, not an oracle. Analytical questions ("is anything
        # illegal in here?") legitimately score low against their own
        # documents — answering from the closest passages beats refusing.
        # The below_threshold flag lets the UI show these as weak matches.
        best = max(r["similarity"] for r in results)
        logger.info(
            f"[Search] Nothing cleared threshold {similarity_threshold} "
            f"(best {best:.3f}) — falling back to top {min(3, top_k)} passages."
        )
        filtered_results = results[: min(3, top_k)]
        for r in filtered_results:
            r.setdefault("metadata", {})["below_threshold"] = True

    # Apply advanced search features if enabled
    if use_hybrid or use_reranking or parsed_query.excluded_terms:
        filtered_results = await search_service.search(
            query, filtered_results, apply_filters=True, rerank=use_reranking
        )

    # Apply query filters (date, court, type)
    filtered_results = search_service.apply_filters(filtered_results, parsed_query)

    # Add rank to results
    for i, result in enumerate(filtered_results):
        result["rank"] = i + 1

    return filtered_results[:top_k]


async def get_document_chunks_directly(
    vector_db,
    document_ids: list[str],
    limit: int = 20,
    user_id: str = "",
    matter_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch chunks directly from documents without semantic search.
    Used for Document Chat Mode - allows users to chat/strategize with selected docs."""
    results = []
    logger.debug(f"[DirectFetch] Fetching chunks for document IDs: {document_ids}")
    try:
        collection = vector_db.collection
        for doc_id in document_ids:
            logger.debug(f"[DirectFetch] Querying ChromaDB for document_id: {doc_id}")
            # Scope to the caller's tenant: owner (user_id) OR a matter they
            # belong to (matter_id). Without any scope the fetch is refused so a
            # document_id alone can never read another tenant's chunks.
            tenant = []
            if user_id:
                tenant.append({"user_id": user_id})
            if matter_ids:
                tenant.append({"matter_id": {"$in": list(matter_ids)}})
            if not tenant:
                raise ValueError(
                    "a user_id or matter_id scope is required to fetch document chunks"
                )
            scope = tenant[0] if len(tenant) == 1 else {"$or": tenant}
            where_clause = {"$and": [{"document_id": doc_id}, scope]}
            chunks = collection.get(
                where=where_clause,
                limit=limit,
                include=["documents", "metadatas"],
            )
            logger.debug(
                f"[DirectFetch] ChromaDB returned {len(chunks.get('ids', []))} chunks for {doc_id}"
            )
            if chunks and chunks.get("ids"):
                for i, chunk_id in enumerate(chunks["ids"]):
                    results.append(
                        {
                            "id": chunk_id,
                            "text": chunks["documents"][i] if chunks.get("documents") else "",
                            "metadata": chunks["metadatas"][i] if chunks.get("metadatas") else {},
                            "similarity": 1.0,
                            "rank": i + 1,
                        }
                    )
            if len(results) >= limit:
                break
    except (ValueError, KeyError, ConnectionError, TimeoutError, OSError, RuntimeError) as e:
        logger.error(f"[DirectFetch] Error fetching chunks: {e}", exc_info=True)
    logger.debug(f"[DirectFetch] Total chunks fetched: {len(results)}")
    return results[:limit]


async def search_case_law(
    query: str,
    limit: int = 5,
    date_from: str | None = None,
    date_to: str | None = None,
    courts: list[str] | None = None,
    question: str | None = None,
    user_keys: Optional["UserAPIKeys"] = None,
) -> list[dict[str, Any]]:
    """Search CourtListener for relevant case law with retry logic.

    ``query`` is the keyword search term (distilled topic keywords, never the
    raw chat message). ``question`` is the user's actual question; when a
    utility LLM is available, every candidate is judged against it and only
    genuinely relevant cases survive — each with an honest 0-1 relevance and
    a short case summary in ``metadata.case_summary``. A keyword hit is not a
    citation.
    """

    async def _search():
        opinions = await courtlistener_service.search_opinions(
            query=query,
            limit=limit,
            cited_gt=2,
        )
        return opinions

    try:
        opinions = await retry_with_backoff(
            _search,
            circuit_breaker_name="courtlistener",
            max_attempts=3,
            retryable_exceptions=(Exception,),
        )
    except CircuitBreakerOpen:
        logger.warning("CourtListener circuit breaker open - case law search unavailable")
        return []
    except (ValueError, KeyError, ConnectionError, TimeoutError, OSError, RuntimeError) as e:
        logger.error(f"CourtListener search failed after retries: {e}")
        return []

    results = []
    for i, opinion in enumerate((opinions or [])[:limit]):
        text = opinion.snippet or ""
        if i < 3 and opinion.id:
            try:

                async def _get_full():
                    return await courtlistener_service.get_opinion(opinion.id)

                full_opinion = await retry_with_backoff(
                    _get_full, circuit_breaker_name="courtlistener", max_attempts=2
                )
                if full_opinion and full_opinion.text:
                    text = full_opinion.text[:2000]
            except (httpx.HTTPError, ConnectionError, TimeoutError):  # nosec B110 - Full text fetch is optional enhancement
                pass

        citation_str = opinion.citation[0] if opinion.citation else "No citation"
        raw_score = opinion.score or 0

        results.append(
            {
                "id": f"courtlistener_{opinion.id}",
                "text": text,
                "metadata": {
                    "filename": f"{opinion.case_name} ({citation_str})",
                    "source": "courtlistener",
                    "doc_type": "case_law",
                    "court": opinion.court,
                    "date_filed": str(opinion.date_filed) if opinion.date_filed else None,
                    "citation": citation_str,
                    "url": opinion.absolute_url,
                    "chunk_index": 0,
                    "raw_score": raw_score,
                    "case_name": opinion.case_name,
                },
                # Set honestly by the relevance judge below; never invented
                # from search rank.
                "similarity": 0.0,
                "rank": i + 1,
            }
        )

    return await _judge_case_law_relevance(question or query, results, user_keys)


def _parse_case_verdicts(raw: str | None, count: int) -> list[dict[str, Any]] | None:
    """Normalize the judge's JSON: one verdict per candidate, by index."""
    try:
        data = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return None
    items = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    verdicts: list[dict[str, Any]] = [
        {"relevant": False, "confidence": 0.0, "summary": ""} for _ in range(count)
    ]
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("i"))
        except (TypeError, ValueError):
            continue
        if not 0 <= idx < count:
            continue
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.0)))
        except (TypeError, ValueError):
            confidence = 0.0
        verdicts[idx] = {
            "relevant": bool(item.get("relevant")),
            "confidence": confidence,
            "summary": str(item.get("summary") or "").strip(),
        }
    return verdicts


async def _judge_case_law_relevance(
    question: str,
    results: list[dict[str, Any]],
    user_keys: Optional["UserAPIKeys"] = None,
) -> list[dict[str, Any]]:
    """ONE utility-LLM call judging every search hit against the question.

    Irrelevant cases are dropped — a lawyer must never be shown a contract
    dispute as authority for a DWI question. Survivors carry the judge's
    confidence as their relevance and a short case summary. On any failure
    the results pass through unjudged with similarity 0 (unknown), never a
    fabricated score.
    """
    if not results:
        return results
    api_key = user_keys.openai if user_keys and getattr(user_keys, "openai", None) else None
    client = make_openai(api_key, async_=True)
    if client is None:
        return results

    case_lines = "\n\n".join(
        f"[{i}] {r['metadata']['case_name']} ({r['metadata']['citation']}, "
        f"{r['metadata'].get('court') or 'court unknown'}):\n"
        f'"{" ".join((r.get("text") or "").split())[:700]}"'
        for i, r in enumerate(results)
    )
    prompt = (
        "You are screening case-law search results for a legal research "
        "question. Keyword search returns noise; your job is to keep only "
        "cases a lawyer would accept as on-topic authority.\n\n"
        f"QUESTION: {question[:500]}\n\n"
        "For EACH numbered case below, using ONLY the text provided:\n"
        '- "relevant": true only if the case genuinely concerns the legal '
        "topic of the question (same offense, doctrine, or issue). A case "
        "about a different subject is false, no matter how it was retrieved.\n"
        '- "confidence": 0-1, how strongly the case bears on the question.\n'
        '- "summary": 2-3 sentences on what the case is about and what the '
        "court held, from the text provided — never invent facts.\n\n"
        'Return STRICT JSON: {"cases":[{"i":0,"relevant":true,'
        '"confidence":0.9,"summary":"..."}]}\n\n'
        f"{UNTRUSTED_CONTENT_RULE}\n\n"
        f"CASES:\n{untrusted_block('Case-law search results', case_lines)}"
    )
    try:
        resp = await openai_chat(
            client,
            model=utility_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        verdicts = _parse_case_verdicts(resp.choices[0].message.content, len(results))
    except Exception as e:  # screening must never break the search
        logger.warning(f"Case-law relevance screening failed, passing results unjudged: {e}")
        return results
    if verdicts is None:
        logger.warning("Case-law relevance screening returned garbage; passing results unjudged")
        return results

    kept: list[dict[str, Any]] = []
    for result, verdict in zip(results, verdicts, strict=False):
        if not verdict["relevant"]:
            continue
        result["similarity"] = verdict["confidence"]
        if verdict["summary"]:
            result["metadata"]["case_summary"] = verdict["summary"]
        kept.append(result)
    dropped = len(results) - len(kept)
    if dropped:
        logger.info(f"Case-law screening dropped {dropped} of {len(results)} off-topic results")
    for rank, result in enumerate(kept, start=1):
        result["rank"] = rank
    return kept
