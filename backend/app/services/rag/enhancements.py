"""Optional RAG enhancements, each toggled per-user via RAGSettings.

These implement the four advanced toggles exposed in the UI:

* query_expansion       -> :func:`expand_query` + :func:`merge_search_results`
* context_compression   -> :func:`compress_context_results`
* citation_verification -> :func:`verify_document_citations`
* source_tracking       -> :func:`annotate_source_locations`

The pure-text helpers (compression, verification, tracking, merging) take no
external dependencies so they are cheap and unit-testable; only query expansion
needs an LLM and degrades gracefully to a no-op on failure.
"""

import logging
import re
from typing import Any

from app.models.schemas import Citation, CitationStatus

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9]{4,}")
_STOPWORDS = {
    "this",
    "that",
    "with",
    "from",
    "into",
    "such",
    "they",
    "their",
    "there",
    "which",
    "while",
    "shall",
    "have",
    "been",
    "were",
    "what",
    "when",
    "would",
    "could",
    "should",
    "about",
    "these",
    "those",
    "than",
    "then",
    "also",
}


def _keywords(text: str) -> set[str]:
    """Lowercase content words (4+ chars, no stopwords) used for overlap scoring."""
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS}


def _result_key(result: dict[str, Any]) -> tuple:
    """Stable identity for a search result so multi-query hits can be deduped."""
    meta = result.get("metadata", {})
    doc_id = meta.get("document_id")
    chunk = meta.get("chunk_index")
    if doc_id is not None and chunk is not None:
        return ("dc", doc_id, chunk)
    return ("txt", (result.get("text", "")[:80]).strip())


# --------------------------------------------------------------------------- #
# Query expansion (multi-query retrieval)
# --------------------------------------------------------------------------- #
async def expand_query(
    query: str,
    openai_client,
    anthropic_client,
    gemini_model,
    model: str,
    max_variants: int = 2,
) -> list[str]:
    """Generate alternative phrasings of ``query`` to broaden retrieval recall.

    Returns ``[original, *variants]``. On any failure (or empty output) it falls
    back to ``[query]`` so retrieval still works.
    """
    system_prompt = (
        "You rewrite a legal search query into alternative phrasings that surface "
        "the same underlying documents. Use synonyms and related legal terminology."
    )
    user_prompt = (
        f"Original query: {query}\n\n"
        f"Write up to {max_variants} alternative search queries, one per line, "
        "no numbering or commentary."
    )

    try:
        from app.services.rag.generation import call_llm

        raw = await call_llm(
            openai_client,
            anthropic_client,
            gemini_model,
            model,
            system_prompt,
            user_prompt,
            200,
            0.0,
        )
    except Exception as e:  # expansion is best-effort
        logger.debug("Query expansion failed, using original query only: %s", e)
        return [query]

    variants: list[str] = []
    seen = {query.strip().lower()}
    for line in (raw or "").splitlines():
        cleaned = line.strip(" \t-•*0123456789.").strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            variants.append(cleaned)
        if len(variants) >= max_variants:
            break

    return [query, *variants]


def merge_search_results(
    result_lists: list[list[dict[str, Any]]], top_k: int
) -> list[dict[str, Any]]:
    """Merge results from several queries, keeping the best similarity per chunk.

    Results are deduped by chunk identity, sorted by similarity, truncated to
    ``top_k`` and re-ranked (1-based ``rank``).
    """
    best: dict[tuple, dict[str, Any]] = {}
    for results in result_lists:
        for r in results:
            key = _result_key(r)
            existing = best.get(key)
            if existing is None or r.get("similarity", 0) > existing.get("similarity", 0):
                best[key] = r

    merged = sorted(best.values(), key=lambda r: r.get("similarity", 0), reverse=True)
    merged = merged[: top_k or len(merged)]
    for i, r in enumerate(merged):
        r["rank"] = i + 1
    return merged


# --------------------------------------------------------------------------- #
# Context compression (extractive)
# --------------------------------------------------------------------------- #
def compress_context_results(
    results: list[dict[str, Any]],
    query: str,
    max_sentences_per_chunk: int = 4,
    min_overlap: int = 1,
) -> list[dict[str, Any]]:
    """Return copies of ``results`` whose text is trimmed to the sentences most
    relevant to ``query`` (by keyword overlap), preserving original order.

    This shrinks the prompt context so more documents fit within the token budget
    without dropping whole chunks. The originals are left untouched (citations
    still show full passages).
    """
    q = _keywords(query)
    if not q:
        return results

    compressed: list[dict[str, Any]] = []
    for r in results:
        text = r.get("text", "")
        sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
        if len(sentences) <= max_sentences_per_chunk:
            compressed.append(r)
            continue

        scored = [(len(q & _keywords(sent)), idx, sent) for idx, sent in enumerate(sentences)]
        kept = [t for t in scored if t[0] >= min_overlap]
        kept.sort(key=lambda t: t[0], reverse=True)
        kept = kept[:max_sentences_per_chunk]
        if not kept:  # nothing matched - fall back to the leading sentences
            kept = scored[:max_sentences_per_chunk]
        kept.sort(key=lambda t: t[1])  # restore reading order

        new_r = dict(r)
        new_r["text"] = " ".join(t[2].strip() for t in kept)
        new_r["compressed"] = True
        compressed.append(new_r)

    return compressed


# --------------------------------------------------------------------------- #
# Citation verification
# --------------------------------------------------------------------------- #
def verify_document_citations(
    citations: list[Citation], answer: str, min_overlap: int = 3
) -> list[Citation]:
    """Cross-check each document citation against the generated ``answer``.

    A citation is treated as genuinely used when its source name appears in the
    answer, or when its passage shares at least ``min_overlap`` content words with
    the answer. Verified citations are marked APPROVED + ``was_cited_by_ai``;
    unsupported ones are reset to PENDING + ``was_cited_by_ai = False`` so the UI
    no longer claims the model relied on them.
    """
    answer_l = (answer or "").lower()
    answer_kw = _keywords(answer or "")

    for c in citations:
        source_stem = (c.source or "").rsplit(".", 1)[0].strip().lower()
        source_hit = bool(source_stem) and source_stem in answer_l
        overlap = len(_keywords(c.passage or "") & answer_kw)
        verified = source_hit or overlap >= min_overlap

        c.was_cited_by_ai = verified
        c.status = CitationStatus.APPROVED if verified else CitationStatus.PENDING
        note = "Verified against answer" if verified else "Not referenced in answer"
        c.notes = f"{c.notes + ' | ' if c.notes else ''}{note}"

    return citations


# --------------------------------------------------------------------------- #
# Source tracking
# --------------------------------------------------------------------------- #
def annotate_source_locations(
    citations: list[Citation], results: list[dict[str, Any]]
) -> list[Citation]:
    """Attach precise source-location details to each citation's ``notes``.

    ``citations`` and ``results`` are parallel (same order). Pulls page and
    character-offset metadata when the indexer recorded it, otherwise reports the
    chunk index.
    """
    for c, r in zip(citations, results):
        meta = r.get("metadata", {}) if isinstance(r, dict) else {}
        parts = [f"chunk #{c.chunk_index + 1}"]
        page = meta.get("page") or meta.get("page_number")
        if page is not None:
            parts.append(f"page {page}")
        start = meta.get("char_start")
        end = meta.get("char_end")
        if start is not None and end is not None:
            parts.append(f"chars {start}-{end}")
        c.notes = f"{c.notes + ' | ' if c.notes else ''}Location: {', '.join(parts)}"

    return citations
