"""
Search helpers layered on top of vector retrieval.

What this module actually does:

- Explicit operator parsing. ``AND`` / ``OR`` / ``NOT`` are operators only
  when typed in UPPERCASE inside a mixed-case query, and ``-term`` excludes a
  term. Ordinary English ("is not paid") is never treated as Boolean.
- Keyword rescoring ("hybrid"). BM25 is computed over the candidates the
  vector search already returned and blended with their similarity. There is
  no separate keyword index: a passage outside the vector candidate pool
  cannot be found by keyword alone.
- Optional cross-encoder reranking, only when ``sentence-transformers`` is
  installed (it is not part of the default install). Without it, results stay
  in blended-score order — no reranking model runs.
- Field filters (``court:``, ``type:``, ``after:`` ...) on result metadata.
"""

import importlib.util
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
    semantic_text: str = ""
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
        """Text to embed / keyword-score: the user's question as typed.

        Only explicit search syntax is removed — recognised ``field:value``
        filters, uppercase AND/OR operators, and excluded (``NOT x`` / ``-x``)
        terms. Stop words, negations in plain English, and unknown
        ``word:value`` tokens are part of the question and stay in.
        """
        return self.semantic_text or self.original


class QueryParser:
    """
    Parses explicit search syntax out of a query without mangling plain English.

    Supports:
    - Uppercase AND / OR / NOT operators (lowercase "and"/"or"/"not" are words)
    - Exclusion prefix: -term
    - Quoted phrases: "willful infringement"
    - Field filters for known fields: court:9th, type:contract, after:2020
    """

    # Words that carry no keyword signal. Used only to keep them out of the
    # required/optional/excluded term lists — never to rewrite the query text.
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

    # Filter-only fields (no metadata mapping of their own).
    FILTER_FIELDS = {"jurisdiction", "after", "from", "date_from", "before", "to", "date_to"}

    _FIELD_PATTERN = re.compile(r'(?<![\w:/])(\w+):("[^"]+"|[^\s":/][^\s"]*)')

    def _is_known_field(self, name: str) -> bool:
        return name in self.FIELD_MAPPINGS or name in self.FILTER_FIELDS

    def parse(self, query: str) -> ParsedQuery:
        """Parse a search query into structured components."""
        result = ParsedQuery(original=query)

        if not query or not query.strip():
            return result

        # Extract field filters (field:value) for KNOWN fields only. Anything
        # else containing a colon ("10:30", "Re:Smith", "Section 3:Term") is
        # ordinary text and is left exactly where it is.
        def _take_field(match: re.Match) -> str:
            field_name = match.group(1).lower()
            if not self._is_known_field(field_name):
                return match.group(0)
            value = match.group(2).strip('"')

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
            return " "

        query_without_fields = self._FIELD_PATTERN.sub(_take_field, query)

        # Quoted phrases are kept verbatim (without the quotes) in the text.
        result.phrases = re.findall(r'"([^"]+)"', query_without_fields)
        query_without_phrases = re.sub(r'"[^"]+"', " ", query_without_fields)

        # Parse remaining tokens; each token carries its own operator/negation.
        tokens = self._tokenize(query_without_phrases)
        result.tokens = tokens

        for token in tokens:
            if token.value.lower() in self.STOP_WORDS:
                continue
            if token.negated:
                result.excluded_terms.append(token.value)
            elif token.operator == BooleanOperator.OR:
                result.optional_terms.append(token.value)
            else:
                result.required_terms.append(token.value)

        result.semantic_text = self._semantic_text(query_without_fields)
        return result

    @staticmethod
    def _operators_enabled(query: str) -> bool:
        """Uppercase operators only count in a mixed-case query.

        An ALL-CAPS message ("WHAT IS NOT COVERED") is shouting, not Boolean.
        """
        return any(ch.islower() for ch in query)

    @staticmethod
    def _exclusion_term(word: str) -> str | None:
        """The term of a ``-term`` exclusion, or None if ``word`` isn't one."""
        if len(word) > 1 and word[0] == "-" and word[1].isalpha():
            return word[1:]
        return None

    def _semantic_text(self, query: str) -> str:
        """``query`` with explicit operators and excluded terms removed.

        Everything else — word order, stop words, punctuation, quoted phrase
        content — is preserved, so a plain-English question is returned
        unchanged (modulo whitespace).
        """
        operators = self._operators_enabled(query)
        kept: list[str] = []
        skip_next = False
        for word in query.replace('"', " ").split():
            if skip_next:
                skip_next = False
                continue
            if operators and word in ("AND", "OR"):
                continue
            if operators and word == "NOT":
                skip_next = True
                continue
            if self._exclusion_term(word) is not None:
                continue
            kept.append(word)
        return " ".join(kept)

    def _tokenize(self, query: str) -> list[QueryToken]:
        """Tokenize query string.

        Operators are recognised only as exact uppercase words (AND, OR, NOT)
        in a mixed-case query; a leading "-" directly attached to a word
        excludes it. Lowercase "and" / "or" / "not" are ordinary words.
        """
        tokens: list[QueryToken] = []
        operators = self._operators_enabled(query)
        current_operator = BooleanOperator.AND
        negated = False

        for word in query.split():
            if operators and word == "AND":
                current_operator = BooleanOperator.AND
                continue
            if operators and word == "OR":
                current_operator = BooleanOperator.OR
                # "a OR b": the term before OR is optional too.
                if tokens and not tokens[-1].negated:
                    tokens[-1].operator = BooleanOperator.OR
                continue
            if operators and word == "NOT":
                negated = True
                continue

            excluded = self._exclusion_term(word)
            if excluded is not None:
                word = excluded
                negated = True

            # Trailing sentence punctuation is not part of the term.
            value = word.strip(".,;:!?()[]")
            if not any(ch.isalnum() for ch in value):
                negated = False
                continue

            tokens.append(QueryToken(value=value, operator=current_operator, negated=negated))

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


def cross_encoder_available() -> bool:
    """True when the optional ``sentence-transformers`` package is installed.

    It is deliberately not in requirements.txt (it pulls PyTorch), so on a
    default install this is False and no reranking model exists.
    """
    try:
        return importlib.util.find_spec("sentence_transformers") is not None
    except (ImportError, ValueError):
        return False


class CrossEncoderReranker:
    """
    Optional cross-encoder reranking.

    Only does anything when ``sentence-transformers`` is installed. Without it
    ``rerank`` is a plain sort by the score already on the results (blended
    hybrid score, else vector similarity) — no model, no extra precision.
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
            logger.info(
                "sentence-transformers is not installed: cross-encoder reranking is "
                "unavailable and results keep their similarity/keyword order."
            )
            self._model_loaded = True  # Mark as loaded to avoid retrying

    @staticmethod
    def _score(result: dict[str, Any]) -> float:
        return result.get("hybrid_score", result.get("similarity", 0)) or 0

    async def rerank(
        self, query: str, results: list[dict[str, Any]], top_k: int = None
    ) -> list[dict[str, Any]]:
        """
        Rerank results with the cross-encoder when one is installed.

        Args:
            query: Search query
            results: Initial retrieval results
            top_k: Number of results to return

        Returns:
            Reranked results; without a model, the same results sorted by
            their existing score.
        """
        if not results:
            return results

        top_k = top_k or settings.top_k

        await self._load_model()

        if self._model is None:
            # No model: keep the existing (blended or similarity) ordering.
            return sorted(results, key=self._score, reverse=True)[:top_k]

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
    Keyword rescoring of vector-search candidates.

    BM25 is computed over the candidates the vector search returned and
    blended with their similarity as a weighted average
    (``keyword_weight`` / ``1 - keyword_weight``). This reorders the candidate
    pool; it does not search a keyword index, so it cannot surface a passage
    the vector search did not return.
    """

    def __init__(self, keyword_weight: float = None):
        self.keyword_weight = keyword_weight or settings.keyword_weight
        self.semantic_weight = 1 - self.keyword_weight
        self.reranker = CrossEncoderReranker()

    async def search(
        self,
        query: str,
        semantic_results: list[dict[str, Any]],
        top_k: int = None,
        rerank: bool = None,
    ) -> list[dict[str, Any]]:
        """
        Rescore vector candidates with BM25 and return them in blended order.

        Args:
            query: Search query
            semantic_results: Results from semantic/vector search
            top_k: Number of results to return
            rerank: Whether to apply cross-encoder reranking (only effective
                when sentence-transformers is installed)

        Returns:
            The candidates, reordered by blended score
        """
        top_k = top_k or settings.top_k
        rerank = rerank if rerank is not None else settings.rerank_enabled

        if not semantic_results:
            return []

        # Score the candidate set with a REQUEST-LOCAL BM25 index built from
        # `semantic_results` on every call. Building it locally (instead of on
        # the shared HybridSearcher singleton) keeps concurrent requests from
        # corrupting each other's keyword scores.
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

        for result in semantic_results:
            doc_id = result.get("id", "")
            semantic_score = result.get("similarity", 0)
            keyword_score = keyword_scores.get(doc_id, 0)

            combined = self.semantic_weight * semantic_score + self.keyword_weight * keyword_score

            result["keyword_score"] = keyword_score
            result["hybrid_score"] = combined
            combined_results.append(result)

        # Sort by hybrid score
        combined_results.sort(key=lambda x: x.get("hybrid_score", 0), reverse=True)

        # Apply reranking if enabled
        if rerank:
            combined_results = await self.reranker.rerank(query, combined_results, top_k)

        return combined_results[:top_k]


class SearchService:
    """
    Query parsing, metadata filters, and keyword rescoring over vector results.
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
        top_k: int = None,
    ) -> list[dict[str, Any]]:
        """
        Rescore and filter vector-search results.

        Args:
            query: Raw search query
            semantic_results: Initial semantic search results
            apply_filters: Whether to apply query filters
            rerank: Whether to apply cross-encoder reranking (if installed)
            top_k: Number of results to return (default settings.top_k)

        Returns:
            Processed and ranked search results
        """
        # Parse query
        parsed = self.parse_query(query)

        # Keyword-rescore the vector candidates
        results = await self.hybrid_searcher.search(
            parsed.get_semantic_query(), semantic_results, top_k=top_k, rerank=rerank
        )

        # Apply filters if enabled
        if apply_filters:
            results = self.apply_filters(results, parsed)

        return results


# Singleton instance
search_service = SearchService()
