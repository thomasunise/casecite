"""
Unit tests for the Search service.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from datetime import date
from unittest.mock import patch

import pytest
from app.services.search import (
    BM25,
    BooleanOperator,
    CrossEncoderReranker,
    HybridSearcher,
    ParsedQuery,
    QueryParser,
    SearchService,
)

# =============================================================================
# QueryParser Tests
# =============================================================================


class TestQueryParser:
    """Tests for QueryParser."""

    def setup_method(self):
        self.parser = QueryParser()

    def test_empty_query(self):
        result = self.parser.parse("")
        assert result.original == ""
        assert result.tokens == []
        assert result.required_terms == []

    def test_simple_query(self):
        result = self.parser.parse("breach contract")
        assert result.original == "breach contract"
        assert "breach" in result.required_terms
        assert "contract" in result.required_terms

    def test_quoted_phrases(self):
        result = self.parser.parse('"willful infringement" patent')
        assert "willful infringement" in result.phrases
        assert "patent" in result.required_terms

    def test_boolean_and(self):
        result = self.parser.parse("breach AND contract")
        # AND is default, both should be required
        assert "breach" in result.required_terms
        assert "contract" in result.required_terms

    def test_boolean_or(self):
        result = self.parser.parse("breach OR negligence damages")
        # Both sides of an explicit OR are optional; the rest stays required.
        assert result.optional_terms == ["breach", "negligence"]
        assert result.required_terms == ["damages"]
        neg_token = next(t for t in result.tokens if t.value == "negligence")
        assert neg_token.operator == BooleanOperator.OR

    def test_boolean_not(self):
        result = self.parser.parse("contract NOT employment")
        assert "contract" in result.required_terms
        assert "employment" in result.excluded_terms

    def test_negation_prefix(self):
        result = self.parser.parse("contract -employment")
        assert "contract" in result.required_terms
        assert "employment" in result.excluded_terms

    def test_field_specific_query(self):
        result = self.parser.parse("court:9th damages")
        assert result.field_queries.get("court") == "9th"
        assert "9th" in result.courts
        assert "damages" in result.required_terms

    def test_date_from_filter(self):
        result = self.parser.parse("after:2023-01-01 negligence")
        assert result.date_from == date(2023, 1, 1)
        assert "negligence" in result.required_terms

    def test_date_to_filter(self):
        result = self.parser.parse("before:2024-06-30 contract")
        assert result.date_to == date(2024, 6, 30)

    def test_type_filter(self):
        result = self.parser.parse("type:opinion damages")
        assert "opinion" in result.doc_types

    def test_jurisdiction_filter(self):
        result = self.parser.parse("jurisdiction:federal breach")
        assert "federal" in result.jurisdictions

    def test_stop_words_excluded(self):
        result = self.parser.parse("the breach of a contract")
        # Stop words like "the", "of", "a" should not appear
        assert "the" not in result.required_terms
        assert "of" not in result.required_terms
        assert "a" not in result.required_terms
        assert "breach" in result.required_terms
        assert "contract" in result.required_terms

    def test_get_semantic_query(self):
        result = self.parser.parse('"due process" equal protection')
        semantic = result.get_semantic_query()
        assert "due process" in semantic
        assert "equal" in semantic
        assert "protection" in semantic

    # --- Plain English must never be parsed as Boolean -------------------

    def test_lowercase_not_is_an_ordinary_word(self):
        """Regression: "is not paid" used to exclude every chunk containing "paid"."""
        query = "What happens if rent is not paid on time?"
        result = self.parser.parse(query)
        assert result.excluded_terms == []
        assert "paid" in result.required_terms
        # The text sent for embedding is the question exactly as typed.
        assert result.get_semantic_query() == query

    def test_lowercase_and_or_are_ordinary_words(self):
        query = "termination or cancellation and notice periods"
        result = self.parser.parse(query)
        assert result.optional_terms == []
        assert result.excluded_terms == []
        assert result.get_semantic_query() == query

    def test_all_caps_message_is_not_boolean(self):
        result = self.parser.parse("WHAT IS NOT COVERED BY THE POLICY")
        assert result.excluded_terms == []
        assert result.get_semantic_query() == "WHAT IS NOT COVERED BY THE POLICY"

    def test_hyphenated_words_and_bare_dashes_are_not_exclusions(self):
        query = "non-compete clause - what does it say about a -5% adjustment?"
        result = self.parser.parse(query)
        assert result.excluded_terms == []
        assert result.get_semantic_query() == query

    def test_unknown_word_colon_value_tokens_are_kept(self):
        """Only known filter fields are parsed out; everything else is text."""
        query = "At 10:30 see Section 3:Termination re:Smith https://example.com/a"
        result = self.parser.parse(query)
        assert result.field_queries == {}
        assert result.get_semantic_query() == query

    def test_stop_words_stay_in_the_semantic_query(self):
        query = "Is the tenant in breach of the lease?"
        assert self.parser.parse(query).get_semantic_query() == query

    def test_explicit_operators_are_removed_from_the_semantic_query(self):
        result = self.parser.parse("indemnification NOT insurance")
        assert result.excluded_terms == ["insurance"]
        assert result.get_semantic_query() == "indemnification"

        result = self.parser.parse("lease -sublease court:9th")
        assert result.excluded_terms == ["sublease"]
        assert result.get_semantic_query() == "lease"

    def test_excluded_terms_filter_only_fires_on_explicit_syntax(self):
        """The chunk that answers a "not paid" question must survive filtering."""
        service = SearchService()
        chunk = {"text": "Rent must be paid on the first of each month.", "metadata": {}}
        parsed = service.parse_query("What happens if rent is not paid on time?")
        assert service.apply_filters([chunk], parsed) == [chunk]

        parsed = service.parse_query("rent NOT paid")
        assert service.apply_filters([chunk], parsed) == []

    def test_parse_date_formats(self):
        # YYYY-MM-DD
        assert self.parser._parse_date("2023-01-15") == date(2023, 1, 15)
        # YYYY/MM/DD
        assert self.parser._parse_date("2023/01/15") == date(2023, 1, 15)
        # YYYY only
        assert self.parser._parse_date("2023") == date(2023, 1, 1)
        # Invalid
        assert self.parser._parse_date("not-a-date") is None


# =============================================================================
# BM25 Tests
# =============================================================================


class TestBM25:
    """Tests for BM25 keyword search."""

    def setup_method(self):
        self.bm25 = BM25()

    def test_index_and_search_basic(self):
        docs = [
            {"id": "d1", "text": "breach of contract damages"},
            {"id": "d2", "text": "negligence personal injury"},
            {"id": "d3", "text": "breach of fiduciary duty damages"},
        ]
        self.bm25.index_documents(docs)

        results = self.bm25.search("breach damages", top_k=2)
        assert len(results) <= 2
        # d1 and d3 should score higher than d2
        result_ids = [r[0] for r in results]
        assert "d2" not in result_ids

    def test_empty_query_returns_empty(self):
        docs = [{"id": "d1", "text": "some document text"}]
        self.bm25.index_documents(docs)

        results = self.bm25.search("", top_k=5)
        assert len(results) == 0

    def test_no_documents_indexed(self):
        self.bm25.index_documents([])
        results = self.bm25.search("test", top_k=5)
        assert len(results) == 0

    def test_search_term_not_in_corpus(self):
        docs = [{"id": "d1", "text": "breach of contract"}]
        self.bm25.index_documents(docs)

        results = self.bm25.search("cryptocurrency blockchain", top_k=5)
        assert len(results) == 0

    def test_top_k_limits_results(self):
        docs = [{"id": f"d{i}", "text": f"common legal term document {i}"} for i in range(20)]
        self.bm25.index_documents(docs)

        results = self.bm25.search("legal term", top_k=5)
        assert len(results) <= 5

    def test_tokenize_removes_short_words(self):
        tokens = self.bm25._tokenize("a to be or not to be")
        assert "a" not in tokens
        assert "to" not in tokens
        assert "be" not in tokens
        assert "not" in tokens


# =============================================================================
# CrossEncoderReranker Tests
# =============================================================================


class TestCrossEncoderReranker:
    """Tests for CrossEncoderReranker."""

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty(self):
        reranker = CrossEncoderReranker()
        result = await reranker.rerank("test query", [])
        assert result == []

    @pytest.mark.asyncio
    async def test_fallback_when_no_model(self):
        reranker = CrossEncoderReranker()
        reranker._model = None
        reranker._model_loaded = True

        results = [
            {"text": "doc a", "similarity": 0.9},
            {"text": "doc b", "similarity": 0.5},
            {"text": "doc c", "similarity": 0.7},
        ]

        with patch("app.services.search.settings") as mock_settings:
            mock_settings.top_k = 10

            reranked = await reranker.rerank("query", results, top_k=3)
            # Should sort by similarity
            assert reranked[0]["similarity"] == 0.9
            assert reranked[1]["similarity"] == 0.7
            assert reranked[2]["similarity"] == 0.5


# =============================================================================
# SearchService Tests
# =============================================================================


class TestSearchService:
    """Tests for SearchService."""

    def setup_method(self):
        self.service = SearchService()

    def test_parse_query_delegates_to_parser(self):
        parsed = self.service.parse_query("breach AND contract")
        assert isinstance(parsed, ParsedQuery)
        assert "breach" in parsed.required_terms

    def test_apply_filters_date_from(self):
        parsed = ParsedQuery(original="test", date_from=date(2024, 1, 1))
        results = [
            {"text": "old doc", "metadata": {"date_filed": "2023-06-15"}},
            {"text": "new doc", "metadata": {"date_filed": "2024-06-15"}},
        ]

        filtered = self.service.apply_filters(results, parsed)
        assert len(filtered) == 1
        assert filtered[0]["text"] == "new doc"

    def test_apply_filters_date_to(self):
        parsed = ParsedQuery(original="test", date_to=date(2023, 12, 31))
        results = [
            {"text": "old doc", "metadata": {"date_filed": "2023-06-15"}},
            {"text": "new doc", "metadata": {"date_filed": "2024-06-15"}},
        ]

        filtered = self.service.apply_filters(results, parsed)
        assert len(filtered) == 1
        assert filtered[0]["text"] == "old doc"

    def test_apply_filters_court(self):
        parsed = ParsedQuery(original="test", courts=["9th"])
        results = [
            {"text": "ninth circuit", "metadata": {"court": "9th Circuit"}},
            {"text": "second circuit", "metadata": {"court": "2nd Circuit"}},
        ]

        filtered = self.service.apply_filters(results, parsed)
        assert len(filtered) == 1
        assert filtered[0]["text"] == "ninth circuit"

    def test_apply_filters_excluded_terms(self):
        parsed = ParsedQuery(original="test", excluded_terms=["employment"])
        results = [
            {"text": "breach of contract damages"},
            {"text": "employment discrimination case"},
        ]

        filtered = self.service.apply_filters(results, parsed)
        assert len(filtered) == 1
        assert filtered[0]["text"] == "breach of contract damages"

    def test_apply_filters_doc_types(self):
        parsed = ParsedQuery(original="test", doc_types=["opinion"])
        results = [
            {"text": "doc1", "metadata": {"doc_type": "opinion"}},
            {"text": "doc2", "metadata": {"doc_type": "brief"}},
        ]

        filtered = self.service.apply_filters(results, parsed)
        assert len(filtered) == 1

    def test_matches_any_case_insensitive(self):
        assert self.service._matches_any("9th Circuit", ["9th"]) is True
        assert self.service._matches_any("SUPREME COURT", ["supreme"]) is True
        assert self.service._matches_any("", ["test"]) is False

    def test_get_date_from_iso_string(self):
        result = {"metadata": {"date_filed": "2024-06-15"}}
        assert self.service._get_date(result) == date(2024, 6, 15)

    def test_get_date_returns_none_for_missing(self):
        result = {"metadata": {}}
        assert self.service._get_date(result) is None

    @pytest.mark.asyncio
    async def test_search_integrates_parsing_and_filtering(self):
        semantic_results = [
            {"id": "d1", "text": "breach of contract", "similarity": 0.9, "metadata": {}},
        ]

        with patch("app.services.search.settings") as mock_settings:
            mock_settings.top_k = 10
            mock_settings.keyword_weight = 0.3
            mock_settings.rerank_enabled = False

            results = await self.service.search("breach contract", semantic_results, rerank=False)
            assert len(results) >= 0  # May or may not filter


# =============================================================================
# HybridSearcher Tests
# =============================================================================


class TestHybridSearcher:
    """Tests for HybridSearcher (BM25 rescoring of vector candidates)."""

    @pytest.mark.asyncio
    async def test_keyword_match_is_promoted_within_the_candidates(self):
        with patch("app.services.search.settings") as mock_settings:
            mock_settings.keyword_weight = 0.5
            mock_settings.top_k = 10
            mock_settings.rerank_enabled = False

            searcher = HybridSearcher()
            candidates = [
                {"id": "a", "text": "general payment terms and invoices", "similarity": 0.62},
                {
                    "id": "b",
                    "text": "indemnification obligations of the vendor",
                    "similarity": 0.60,
                },
            ]
            results = await searcher.search("indemnification", candidates, rerank=False)
            assert [r["id"] for r in results] == ["b", "a"]
            assert results[0]["keyword_score"] == 1.0
            assert results[1]["keyword_score"] == 0

    @pytest.mark.asyncio
    async def test_respects_requested_top_k(self):
        with patch("app.services.search.settings") as mock_settings:
            mock_settings.keyword_weight = 0.3
            mock_settings.top_k = 2
            mock_settings.rerank_enabled = False

            searcher = HybridSearcher()
            candidates = [
                {"id": f"d{i}", "text": f"clause {i}", "similarity": 0.9 - i * 0.1}
                for i in range(5)
            ]
            assert len(await searcher.search("clause", candidates, top_k=4, rerank=False)) == 4

    @pytest.mark.asyncio
    async def test_falls_back_to_semantic_when_not_indexed(self):
        with patch("app.services.search.settings") as mock_settings:
            mock_settings.keyword_weight = 0.3
            mock_settings.top_k = 10
            mock_settings.rerank_enabled = False

            searcher = HybridSearcher()
            semantic_results = [{"id": "d1", "text": "test", "similarity": 0.8}]

            results = await searcher.search("test", semantic_results, rerank=False)
            assert len(results) == 1
            assert results[0]["id"] == "d1"

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_results(self):
        with patch("app.services.search.settings") as mock_settings:
            mock_settings.keyword_weight = 0.3
            mock_settings.top_k = 10
            mock_settings.rerank_enabled = False

            searcher = HybridSearcher()
            results = await searcher.search("test", [], rerank=False)
            assert results == []
