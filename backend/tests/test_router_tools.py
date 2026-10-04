"""
Integration tests for the ToolsRouter (/tools).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _bypass_session_validation():
    """Bypass session validation so auth_headers work in tests."""
    with patch("app.middleware.security.session_manager.validate_session", return_value=True):
        yield


class TestToolsRouter:
    """Tests for /api/v1/tools endpoints."""

    # ==================== Case Search ====================

    def test_search_cases_no_auth(self, client):
        """Case search requires authentication — anonymous requests get 401."""
        with patch(
            "app.routers.tools.legal_tools.search_cases",
            new_callable=AsyncMock,
            return_value={
                "results": [],
                "total": 0,
                "next_cursor": None,
            },
        ):
            resp = client.get(
                "/api/v1/tools/cases/search",
                params={"q": "first amendment"},
            )
            assert resp.status_code == 401

    def test_search_cases_with_auth(self, client, auth_headers):
        """Search cases with authentication."""
        with patch(
            "app.routers.tools.legal_tools.search_cases",
            new_callable=AsyncMock,
            return_value={
                "results": [{"case_name": "Test v. Case"}],
                "total": 1,
                "next_cursor": "abc123",
            },
        ):
            resp = client.get(
                "/api/v1/tools/cases/search",
                params={"q": "due process", "page_size": 10},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1

    def test_get_case_detail(self, client, auth_headers):
        """Get full case details by opinion ID."""
        with patch(
            "app.routers.tools.legal_tools.get_case_detail",
            new_callable=AsyncMock,
            return_value={
                "id": 12345,
                "case_name": "Smith v. Jones",
                "opinion_text": "The court finds...",
            },
        ):
            resp = client.get("/api/v1/tools/cases/12345", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["case_name"] == "Smith v. Jones"

    def test_get_case_detail_not_found(self, client, auth_headers):
        """Case detail returns 404 if not found."""
        with patch(
            "app.routers.tools.legal_tools.get_case_detail",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/api/v1/tools/cases/999999", headers=auth_headers)
            assert resp.status_code == 404

    # ==================== Citation Validator ====================

    def test_validate_citation(self, client, auth_headers):
        """Validate a single citation."""
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "citation": "410 U.S. 113",
            "is_good_law": True,
            "warning_level": "none",
            "positive_citations": 500,
            "negative_citations": 2,
        }
        with patch(
            "app.routers.tools.courtlistener_service.validate_citation",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.get(
                "/api/v1/tools/validate-citation",
                params={"citation": "410 U.S. 113"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["is_good_law"] is True

    # ==================== Judge Analyzer (moved to /judge-intel) ====================

    def test_search_judges(self, client, auth_headers):
        """Search for judges by name (now served by the judge-intel router)."""
        with patch(
            "app.routers.judge_intel.judge_intel.search_judges",
            new_callable=AsyncMock,
            return_value={
                "judges": [{"id": 1, "name": "Judge Smith", "court": "ca9"}],
                "count": 1,
                "total_available": 1,
            },
        ):
            resp = client.get(
                "/api/v1/judge-intel/search",
                params={"q": "Smith"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 1

    def test_get_judge(self, client, auth_headers):
        """Get detailed judge profile (now served by the judge-intel router)."""
        with patch(
            "app.routers.judge_intel.judge_intel.get_judge_profile",
            new_callable=AsyncMock,
            return_value={
                "id": 1,
                "name": "Judge Smith",
                "court": "ca9",
                "appointed_by": "President X",
            },
        ):
            resp = client.get("/api/v1/judge-intel/profile/1", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["name"] == "Judge Smith"

    def test_get_judge_not_found(self, client, auth_headers):
        """Judge profile returns 404 if the judge is not in the local cache."""
        with patch(
            "app.routers.judge_intel.judge_intel.get_judge_profile",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/api/v1/judge-intel/profile/999", headers=auth_headers)
            assert resp.status_code == 404

    # ==================== Precedent Finder ====================

    def test_find_precedents(self, client, auth_headers):
        """Find most-cited cases on a topic."""
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "case_name": "Leading Case",
            "citation_count": 500,
        }
        with patch(
            "app.routers.tools.legal_tools.find_precedents",
            new_callable=AsyncMock,
            return_value=[mock_result],
        ):
            resp = client.get(
                "/api/v1/tools/precedents",
                params={"topic": "due process", "min_citations": 10},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 1

    def test_find_precedents_empty(self, client, auth_headers):
        """Precedent finder returns an empty result cleanly."""
        with patch(
            "app.routers.tools.legal_tools.find_precedents",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = client.get(
                "/api/v1/tools/precedents",
                params={"topic": "habeas corpus"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["count"] == 0

    # ==================== Docket Search ====================

    def test_search_dockets(self, client, auth_headers):
        """Search court dockets."""
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {"docket_number": "2:24-cv-01234"}
        with patch(
            "app.routers.tools.legal_tools.search_dockets",
            new_callable=AsyncMock,
            return_value=[mock_result],
        ):
            resp = client.get(
                "/api/v1/tools/dockets",
                params={"query": "Apple v. Samsung"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["count"] == 1

    # ==================== Oral Arguments ====================

    def test_search_oral_arguments(self, client, auth_headers):
        """Search oral argument recordings."""
        with patch(
            "app.routers.tools.legal_tools.search_oral_arguments",
            new_callable=AsyncMock,
            return_value=[{"case": "Test v. Case", "audio_url": "https://example.com/audio.mp3"}],
        ):
            resp = client.get(
                "/api/v1/tools/oral-arguments",
                params={"query": "second amendment"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 1

    # ==================== Legal Trends ====================

    def test_analyze_trend(self, client, auth_headers):
        """Analyze legal trends on a topic."""
        with patch(
            "app.routers.tools.legal_tools.analyze_legal_trend",
            new_callable=AsyncMock,
            return_value={
                "topic": "AI regulation",
                "years": {"2020": 10, "2021": 15, "2022": 25},
            },
        ):
            resp = client.get(
                "/api/v1/tools/trends",
                params={"topic": "AI regulation", "start_year": 2020},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["topic"] == "AI regulation"


class TestAuthGating:
    """/tools and /legal-docs/courts always require authentication (no anonymous path)."""

    def test_anonymous_401(self, client):
        """Anonymous /tools requests are rejected regardless of DEBUG."""
        resp = client.get("/api/v1/tools/cases/search", params={"q": "x"})
        assert resp.status_code == 401

    def test_authenticated_user_allowed(self, client, auth_headers):
        with patch(
            "app.routers.tools.legal_tools.search_cases",
            new_callable=AsyncMock,
            return_value={"results": [], "total": 0, "next_cursor": None},
        ):
            resp = client.get("/api/v1/tools/cases/search", params={"q": "x"}, headers=auth_headers)
        assert resp.status_code == 200

    def test_courts_anonymous_401(self, client):
        """/legal-docs/courts follows the same auth policy as /tools."""
        resp = client.get("/api/v1/legal-docs/courts")
        assert resp.status_code == 401

    def test_courts_authenticated_allowed(self, client, auth_headers):
        with patch("app.routers.legal_docs.get_all_courts", return_value=[]):
            resp = client.get("/api/v1/legal-docs/courts", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["count"] == 0
