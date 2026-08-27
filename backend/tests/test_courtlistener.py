"""
Unit tests for the CourtListener integration service.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCourtListenerService:
    """Tests for CourtListenerService."""

    def _make_service(self, token="test-token"):
        """Create service with mocked settings."""
        with patch("app.services.courtlistener.settings") as mock_settings:
            mock_settings.courtlistener_api_token = token
            from app.services.courtlistener import CourtListenerService

            svc = CourtListenerService()
        return svc

    # ------------------------------------------------------------------ #
    # _check_token
    # ------------------------------------------------------------------ #

    def test_check_token_raises_without_token(self):
        """Should raise ValueError when no token is configured."""
        svc = self._make_service(token="")
        with pytest.raises(ValueError, match="API token required"):
            svc._check_token()

    def test_check_token_passes_with_token(self):
        """Should not raise when token is configured."""
        svc = self._make_service(token="valid-token")
        svc._check_token()  # Should not raise

    # ------------------------------------------------------------------ #
    # _parse_date
    # ------------------------------------------------------------------ #

    def test_parse_date_valid(self):
        """Should parse ISO date string."""
        svc = self._make_service()
        result = svc._parse_date("2024-06-15")
        assert result == date(2024, 6, 15)

    def test_parse_date_none(self):
        """Should return None for None input."""
        svc = self._make_service()
        assert svc._parse_date(None) is None

    def test_parse_date_invalid(self):
        """Should return None for invalid string."""
        svc = self._make_service()
        assert svc._parse_date("not-a-date") is None

    def test_parse_date_with_z_suffix(self):
        """Should handle Z suffix in date strings."""
        svc = self._make_service()
        result = svc._parse_date("2024-06-15T00:00:00Z")
        assert result == date(2024, 6, 15)

    # ------------------------------------------------------------------ #
    # _looks_like_citation
    # ------------------------------------------------------------------ #

    def test_looks_like_citation_true(self):
        """Should recognize standard legal citation patterns."""
        svc = self._make_service()
        assert svc._looks_like_citation("410 U.S. 113") is True
        assert svc._looks_like_citation("123 F.3d 456") is True

    def test_looks_like_citation_false(self):
        """Should reject non-citation text."""
        svc = self._make_service()
        assert svc._looks_like_citation("Brown v. Board of Education") is False
        assert svc._looks_like_citation("some random text") is False

    # ------------------------------------------------------------------ #
    # _analyze_treatment
    # ------------------------------------------------------------------ #

    def test_analyze_treatment_negative(self):
        """Should detect negative treatment terms."""
        from app.services.courtlistener import CitationTreatment

        svc = self._make_service()
        assert (
            svc._analyze_treatment("The court overruled the prior holding.")
            == CitationTreatment.NEGATIVE
        )
        assert (
            svc._analyze_treatment("We rejected the reasoning of that precedent in Smith.")
            == CitationTreatment.NEGATIVE
        )
        # Bare "rejected" is everyday opinion prose, not treatment of the cited case.
        assert (
            svc._analyze_treatment("The court rejected defendant's argument, citing Roe.")
            == CitationTreatment.NEUTRAL
        )
        # "Overruled on other grounds" leaves the cited point standing.
        assert (
            svc._analyze_treatment("Roe, overruled on other grounds by Casey, controls here.")
            == CitationTreatment.CAUTION
        )

    def test_analyze_treatment_positive(self):
        """Should detect positive treatment terms."""
        from app.services.courtlistener import CitationTreatment

        svc = self._make_service()
        assert (
            svc._analyze_treatment("The court followed and affirmed the rule.")
            == CitationTreatment.POSITIVE
        )
        assert (
            svc._analyze_treatment("This rule was adopted by the court.")
            == CitationTreatment.POSITIVE
        )

    def test_analyze_treatment_caution(self):
        """Should detect caution treatment terms."""
        from app.services.courtlistener import CitationTreatment

        svc = self._make_service()
        assert (
            svc._analyze_treatment("The case was distinguished from the facts.")
            == CitationTreatment.CAUTION
        )
        assert (
            svc._analyze_treatment("Courts have questioned this holding.")
            == CitationTreatment.CAUTION
        )

    def test_analyze_treatment_neutral(self):
        """Should return neutral when no treatment indicators found."""
        from app.services.courtlistener import CitationTreatment

        svc = self._make_service()
        assert svc._analyze_treatment("The court cited the case.") == CitationTreatment.NEUTRAL

    # ------------------------------------------------------------------ #
    # _get_courts_for_jurisdiction
    # ------------------------------------------------------------------ #

    def test_get_courts_federal(self):
        """Should return all federal courts for 'federal' jurisdiction."""
        svc = self._make_service()
        courts = svc._get_courts_for_jurisdiction("federal")
        assert "scotus" in courts
        assert "ca9" in courts
        assert len(courts) == 14

    def test_get_courts_immigration(self):
        """Should return BIA courts for 'immigration' jurisdiction."""
        svc = self._make_service()
        courts = svc._get_courts_for_jurisdiction("immigration")
        assert "bia" in courts

    def test_get_courts_unknown(self):
        """Should return empty list for unknown jurisdiction."""
        svc = self._make_service()
        courts = svc._get_courts_for_jurisdiction("unknown_place")
        assert courts == []

    # ------------------------------------------------------------------ #
    # search_opinions
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_search_opinions_success(self):
        """Should return list of Opinion objects from API results."""
        svc = self._make_service()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 12345,
                    "absolute_url": "/opinion/12345/smith-v-jones/",
                    "caseName": "Smith v. Jones",
                    "caseNameShort": "Smith",
                    "citation": ["123 F.3d 456"],
                    "court": "Ninth Circuit",
                    "court_id": "ca9",
                    "dateFiled": "2023-06-15",
                    "docketNumber": "22-1234",
                    "judge": "Smith, J.",
                    "snippet": "The court held...",
                    "score": 15.5,
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = await svc.search_opinions("specialty occupation")

        assert len(results) == 1
        assert results[0].case_name == "Smith v. Jones"
        assert results[0].court_id == "ca9"

    @pytest.mark.asyncio
    async def test_search_opinions_v4_nested_shape(self):
        """v4 search results are cluster-shaped: the opinion id, snippet and
        score live in the nested "opinions" list / "meta" object. The parser
        must surface them — a 0 id makes every downstream get_opinion() 404."""
        svc = self._make_service()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    # no top-level "id", "snippet" or "score" in v4
                    "absolute_url": "/opinion/901260/convenience-center-inc-v-cole/",
                    "caseName": "Convenience Center, Inc. v. Cole",
                    "citation": ["678 N.W.2d 774"],
                    "cluster_id": 901260,
                    "court": "South Dakota Supreme Court",
                    "court_id": "sd",
                    "dateFiled": "2004-03-31",
                    "meta": {"score": {"bm25": 31.23}},
                    "opinions": [
                        {"id": 901260, "snippet": "The court held...", "type": "combined-opinion"}
                    ],
                },
                {
                    # a result with no resolvable opinion id is skipped, not id=0
                    "absolute_url": "/opinion/999/broken/",
                    "caseName": "Broken v. Result",
                    "court": "Nowhere",
                    "court_id": "xx",
                    "opinions": [],
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = await svc.search_opinions("termination for convenience")

        assert len(results) == 1
        assert results[0].id == 901260
        assert results[0].snippet == "The court held..."
        assert results[0].score == 31.23

    @pytest.mark.asyncio
    async def test_search_opinions_empty(self):
        """Should return empty list when no results found."""
        svc = self._make_service()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"results": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = await svc.search_opinions("nonexistent case xyz")

        assert results == []

    # ------------------------------------------------------------------ #
    # get_opinion
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_get_opinion_success(self):
        """Should return Opinion for a valid ID."""
        svc = self._make_service()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "id": 12345,
            "absolute_url": "/opinion/12345/",
            "case_name": "Smith v. Jones",
            "case_name_short": "Smith",
            "court": "ca9",
            "date_filed": "2023-06-15",
            "plain_text": "The court held that...",
            "html_with_citations": "<p>The court held that...</p>",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await svc.get_opinion(12345)

        assert result is not None
        assert result.case_name == "Smith v. Jones"
        assert result.text == "The court held that..."

    @pytest.mark.asyncio
    async def test_get_opinion_not_found(self):
        """Should return None for 404 response."""
        svc = self._make_service()

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await svc.get_opinion(99999)

        assert result is None

    # ------------------------------------------------------------------ #
    # search_by_topic
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_search_by_topic_expands_known_topics(self):
        """Should expand known topics into broader search queries."""
        svc = self._make_service()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"results": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await svc.search_by_topic("h1b")

        # Verify the expanded query was used (contains H-1B terminology)
        call_args = mock_client.get.call_args
        params = call_args.kwargs.get("params", call_args[1].get("params", {}))
        assert "H-1B" in params.get("q", "") or "specialty occupation" in params.get("q", "")
