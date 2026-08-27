"""
Advanced Search Module - Enterprise-Grade Search Capabilities

Provides:
- Boolean query parsing (AND, OR, NOT, phrases)
- Hybrid search (semantic + keyword BM25)
- Field-specific search
- Date range, court, and document type filters
- Cross-encoder reranking
- Query expansion
"""

import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class BooleanOperator(Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    PHRASE = "PHRASE"


@dataclass
class QueryToken:
    """Represents a parsed query token."""

    value: str
    operator: BooleanOperator = BooleanOperator.AND
    field: str | None = None  # For field-specific search
    is_phrase: bool = False
    negated: bool = False


@dataclass
class ParsedQuery:
    """Structured representation of a parsed search query."""

    original: str
    tokens: list[QueryToken] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)
    required_terms: list[str] = field(default_factory=list)  # AND terms
    optional_terms: list[str] = field(default_factory=list)  # OR terms
    excluded_terms: list[str] = field(default_factory=list)  # NOT terms
    field_queries: dict[str, str] = field(default_factory=dict)

    # Filters
    date_from: date | None = None
    date_to: date | None = None
    courts: list[str] = field(default_factory=list)
    doc_types: list[str] = field(default_factory=list)
    jurisdictions: list[str] = field(default_factory=list)

    def get_semantic_query(self) -> str:
        """Get the query optimized for semantic search."""
        parts = []
        parts.extend(self.phrases)
        parts.extend(self.required_terms)
        parts.extend(self.optional_terms)
        return " ".join(parts)

    def get_keyword_query(self) -> str:
        """Get the query for keyword/BM25 search."""
        return self.original


class QueryParser:
    """
    Parses legal search queries with Boolean operators.

    Supports:
    - AND, OR, NOT operators
    - Quoted phrases: "willful infringement"
    - Field-specific: case_name:Smith, court:9th
    - Parentheses for grouping (future)
    """

    # Legal-specific stop words to ignore
    STOP_WORDS = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "been",
        "be",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
    }

    # Field mappings for field-specific search
    FIELD_MAPPINGS = {
        "case": "case_name",
        "case_name": "case_name",
        "court": "court",
        "judge": "judge",
        "date": "date_filed",
        "year": "year",
        "citation": "citation",
        "cite": "citation",
        "type": "doc_type",
        "source": "source",
        "filename": "filename",
    }

    def parse(self, query: str) -> ParsedQuery:
        """Parse a search query into structured components."""
        result = ParsedQuery(original=query)

        if not query or not query.strip():
            return result

        # Extract quoted phrases first
        phrases = re.findall(r'"([^"]+)"', query)
        result.phrases = phrases

        # Remove phrases from query for further parsing
        query_without_phrases = re.sub(r'"[^"]+"', " ", query)

        # Extract field-specific queries (field:value)
        field_pattern = r'(\w+):(\S+|"[^"]+")'
        for match in re.finditer(field_pattern, query_without_phrases):
            field_name, value = match.groups()
            field_name = field_name.lower()
            value = value.strip('"')

            if field_name in self.FIELD_MAPPINGS:
                result.field_queries[self.FIELD_MAPPINGS[field_name]] = value

            # Handle special filter fields
            if field_name == "court":
                result.courts.append(value)
            elif field_name == "type":
                result.doc_types.append(value)
            elif field_name == "jurisdiction":
                result.jurisdictions.append(value)
            elif field_name in ("after", "from", "date_from"):
                result.date_from = self._parse_date(value)
            elif field_name in ("before", "to", "date_to"):
                result.date_to = self._parse_date(value)

        # Remove field queries
        query_without_fields = re.sub(field_pattern, " ", query_without_phrases)

        # Parse remaining tokens with Boolean operators
        tokens = self._tokenize(query_without_fields)
        result.tokens = tokens

        # Categorize terms
        current_operator = BooleanOperator.AND
        for token in tokens:
            if token.value.upper() == "AND":
                current_operator = BooleanOperator.AND
            elif token.value.upper() == "OR":
                current_operator = BooleanOperator.OR
            elif token.value.upper() == "NOT":
                current_operator = BooleanOperator.NOT
            elif token.value.lower() not in self.STOP_WORDS:
                if current_operator == BooleanOperator.NOT or token.negated:
                    result.excluded_terms.append(token.value)
                elif current_operator == BooleanOperator.OR:
                    result.optional_terms.append(token.value)
                else:
                    result.required_terms.append(token.value)

        return result

    def _tokenize(self, query: str) -> list[QueryToken]:
        """Tokenize query string."""
        tokens = []
        words = query.split()
        current_operator = BooleanOperator.AND
        negated = False

        for word in words:
            word = word.strip()
            if not word:
                continue

            upper_word = word.upper()

            # Check for operators
            if upper_word == "AND":
                current_operator = BooleanOperator.AND
                continue
            elif upper_word == "OR":
                current_operator = BooleanOperator.OR
                continue
            elif upper_word in ("NOT", "-"):
                negated = True
                continue

            # Check for negation prefix
            if word.startswith("-"):
                word = word[1:]
                negated = True

            # Create token
            token = QueryToken(value=word, operator=current_operator, negated=negated)
            tokens.append(token)

            # Reset negation
            negated = False
            current_operator = BooleanOperator.AND

        return tokens

    def _parse_date(self, value: str) -> date | None:
        """Parse date from various formats."""
        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%m/%d/%Y",
            "%Y",
        ]
        for fmt in formats:
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.date()
            except ValueError:
                continue
        return None


class BM25:
    """
    BM25 (Best Matching 25) keyword search implementation.

    Used for hybrid search combining semantic + keyword matching.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_lengths: dict[str, int] = {}
        self.avg_doc_length: float = 0
        self.doc_freqs: dict[str, int] = defaultdict(int)
        self.idf: dict[str, float] = {}
        self.doc_term_freqs: dict[str, dict[str, int]] = {}
        self.num_docs: int = 0

    def index_documents(self, documents: list[dict[str, Any]]):
        """Index documents for BM25 search."""
        self.num_docs = len(documents)
        total_length = 0

        # First pass: collect statistics
        term_doc_counts: dict[str, int] = defaultdict(int)

        for doc in documents:
            doc_id = doc.get("id", str(hash(doc.get("text", ""))))
            text = doc.get("text", "").lower()
            terms = self._tokenize(text)

            self.doc_lengths[doc_id] = len(terms)
            total_length += len(terms)

            # Term frequencies for this document
            term_freqs: dict[str, int] = defaultdict(int)
            seen_terms: set[str] = set()

            for term in terms:
                term_freqs[term] += 1
                if term not in seen_terms:
                    term_doc_counts[term] += 1
                    seen_terms.add(term)

            self.doc_term_freqs[doc_id] = dict(term_freqs)

        # Calculate average document length
        self.avg_doc_length = total_length / self.num_docs if self.num_docs > 0 else 0

        # Calculate IDF for each term
        for term, doc_count in term_doc_counts.items():
            self.idf[term] = math.log((self.num_docs - doc_count + 0.5) / (doc_count + 0.5) + 1)

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Search for documents matching query."""
        query_terms = self._tokenize(query.lower())
        scores: dict[str, float] = defaultdict(float)

        for doc_id, term_freqs in self.doc_term_freqs.items():
            doc_len = self.doc_lengths[doc_id]

            for term in query_terms:
                if term not in term_freqs:
                    continue

                tf = term_freqs[term]
                idf = self.idf.get(term, 0)

                # BM25 formula
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_length)
                scores[doc_id] += idf * numerator / denominator

        # Sort by score and return top_k
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization."""
        # Remove punctuation and split
        text = re.sub(r"[^\w\s]", " ", text)
        return [w for w in text.split() if len(w) > 2]


class CrossEncoderReranker:
    """
    Cross-encoder reranking for improved relevance.

    Uses a more expensive model to rerank top candidates
    from initial retrieval for better precision.
    """

    def __init__(self):
        self._model = None
        self._model_loaded = False

    async def _load_model(self):
        """Lazy load the cross-encoder model."""
        if self._model_loaded:
            return

        try:
            # Try to load sentence-transformers cross-encoder
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            self._model_loaded = True
            logger.info("Cross-encoder model loaded successfully")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. "
                "Reranking will use similarity scores only. "
                "Install with: pip install sentence-transformers"
            )
            self._model_loaded = True  # Mark as loaded to avoid retrying

    async def rerank(
        self, query: str, results: list[dict[str, Any]], top_k: int = None
    ) -> list[dict[str, Any]]:
        """
        Rerank results using cross-encoder.

        Args:
            query: Search query
            results: Initial retrieval results
            top_k: Number of results to return

        Returns:
            Reranked results
        """
        if not results:
            return results

        top_k = top_k or settings.top_k

        await self._load_model()

        if self._model is None:
            # Fallback: use original similarity scores
            return sorted(results, key=lambda x: x.get("similarity", 0), reverse=True)[:top_k]

        # Prepare query-document pairs
        pairs = [(query, r.get("text", "")) for r in results]

        try:
            # Get cross-encoder scores
            scores = self._model.predict(pairs)

            # Add rerank scores to results
            for i, result in enumerate(results):
                result["rerank_score"] = float(scores[i])
                # Combined score: weighted average of similarity and rerank
                original_sim = result.get("similarity", 0)
                result["combined_score"] = 0.3 * original_sim + 0.7 * (scores[i] + 1) / 2

            # Sort by combined score
            reranked = sorted(results, key=lambda x: x.get("combined_score", 0), reverse=True)
            return reranked[:top_k]

        except (ValueError, KeyError, ConnectionError, TimeoutError, OSError, RuntimeError) as e:
            logger.error(f"Reranking failed: {e}")
            return results[:top_k]


class HybridSearcher:
    """
    Combines semantic search with BM25 keyword search.

    Uses Reciprocal Rank Fusion (RRF) to merge results.
    """

    def __init__(self, keyword_weight: float = None):
        self.keyword_weight = keyword_weight or settings.keyword_weight
        self.semantic_weight = 1 - self.keyword_weight
        self.bm25 = BM25()
        self.reranker = CrossEncoderReranker()
        self._indexed = False

    def index_documents(self, documents: list[dict[str, Any]]):
        """Index documents for keyword search."""
        self.bm25.index_documents(documents)
        self._indexed = True

    async def search(
        self,
        query: str,
        semantic_results: list[dict[str, Any]],
        top_k: int = None,
        rerank: bool = None,
    ) -> list[dict[str, Any]]:
        """
        Perform hybrid search combining semantic and keyword results.

        Args:
            query: Search query
            semantic_results: Results from semantic/vector search
            top_k: Number of results to return
            rerank: Whether to apply cross-encoder reranking

        Returns:
            Merged and ranked results
        """
        top_k = top_k or settings.top_k
        rerank = rerank if rerank is not None else settings.rerank_enabled

        if not semantic_results:
            return []

        # Score the candidate set with a REQUEST-LOCAL BM25 index. The keyword
        # half of hybrid search fuses BM25 rank over exactly the vector
        # candidates, so the index must be built from `semantic_results` on
        # every call. Building it locally (instead of mutating the shared
        # HybridSearcher singleton) keeps concurrent requests from corrupting
        # each other's keyword scores. Historically this indexing step was
        # never invoked, so `_indexed` stayed False and hybrid silently
        # degraded to semantic-only — this restores the keyword contribution.
        bm25 = BM25()
        bm25.index_documents(semantic_results)

        # Get keyword search results
        keyword_results = bm25.search(query, top_k=top_k * 2)
        keyword_scores = {doc_id: score for doc_id, score in keyword_results}

        # Normalize keyword scores
        max_keyword = max(keyword_scores.values()) if keyword_scores else 1
        keyword_scores = {k: v / max_keyword for k, v in keyword_scores.items()}

        # Combine scores using weighted average
        combined_results = []
        seen_ids = set()

        for result in semantic_results:
            doc_id = result.get("id", "")
            semantic_score = result.get("similarity", 0)
            keyword_score = keyword_scores.get(doc_id, 0)

            combined = self.semantic_weight * semantic_score + self.keyword_weight * keyword_score

            result["keyword_score"] = keyword_score
            result["hybrid_score"] = combined
            combined_results.append(result)
            seen_ids.add(doc_id)

        # Sort by hybrid score
        combined_results.sort(key=lambda x: x.get("hybrid_score", 0), reverse=True)

        # Apply reranking if enabled
        if rerank:
            combined_results = await self.reranker.rerank(query, combined_results, top_k)

        return combined_results[:top_k]


class SearchService:
    """
    Main search service combining all search capabilities.
    """

    def __init__(self):
        self.parser = QueryParser()
        self.hybrid_searcher = HybridSearcher()

    def parse_query(self, query: str) -> ParsedQuery:
        """Parse a search query."""
        return self.parser.parse(query)

    def apply_filters(
        self, results: list[dict[str, Any]], parsed_query: ParsedQuery
    ) -> list[dict[str, Any]]:
        """Apply filters from parsed query to results."""
        filtered = results

        # Date filters
        if parsed_query.date_from:
            filtered = [
                r
                for r in filtered
                if self._get_date(r) and self._get_date(r) >= parsed_query.date_from
            ]

        if parsed_query.date_to:
            filtered = [
                r
                for r in filtered
                if self._get_date(r) and self._get_date(r) <= parsed_query.date_to
            ]

        # Court filter
        if parsed_query.courts:
            filtered = [
                r
                for r in filtered
                if self._matches_any(r.get("metadata", {}).get("court", ""), parsed_query.courts)
            ]

        # Document type filter
        if parsed_query.doc_types:
            filtered = [
                r
                for r in filtered
                if self._matches_any(
                    r.get("metadata", {}).get("doc_type", ""), parsed_query.doc_types
                )
            ]

        # Excluded terms filter
        if parsed_query.excluded_terms:
            filtered = [
                r
                for r in filtered
                if not any(
                    term.lower() in r.get("text", "").lower()
                    for term in parsed_query.excluded_terms
                )
            ]

        return filtered

    def _get_date(self, result: dict[str, Any]) -> date | None:
        """Extract date from result."""
        metadata = result.get("metadata", {})
        date_str = metadata.get("date_filed") or metadata.get("created_at")
        if date_str:
            try:
                if isinstance(date_str, str):
                    return datetime.fromisoformat(date_str.replace("Z", "")).date()
                elif isinstance(date_str, date):
                    return date_str
            except (ValueError, TypeError):
                pass
        return None

    def _matches_any(self, value: str, patterns: list[str]) -> bool:
        """Check if value matches any pattern (case-insensitive)."""
        if not value:
            return False
        value_lower = value.lower()
        return any(p.lower() in value_lower for p in patterns)

    async def search(
        self,
        query: str,
        semantic_results: list[dict[str, Any]],
        apply_filters: bool = True,
        rerank: bool = None,
    ) -> list[dict[str, Any]]:
        """
        Perform advanced search with all features.

        Args:
            query: Raw search query
            semantic_results: Initial semantic search results
            apply_filters: Whether to apply query filters
            rerank: Whether to apply reranking

        Returns:
            Processed and ranked search results
        """
        # Parse query
        parsed = self.parse_query(query)

        # Perform hybrid search
        results = await self.hybrid_searcher.search(
            parsed.get_semantic_query(), semantic_results, rerank=rerank
        )

        # Apply filters if enabled
        if apply_filters:
            results = self.apply_filters(results, parsed)

        return results


# Singleton instance
search_service = SearchService()
