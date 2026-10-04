"""
Integration tests for Judge Intel router (/api/v1/judge-intel).
"""

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.usefixtures("no_rate_limit")


class TestJudgeIntelRouter:
    """Tests for /api/v1/judge-intel endpoints."""

    def test_search_no_auth(self, client):
        """GET /api/v1/judge-intel/search without auth returns 401."""
        response = client.get("/api/v1/judge-intel/search", params={"q": "Smith"})
        assert response.status_code == 401

    def test_delete_profile_requires_admin(self, client, non_admin_headers):
        """DELETE /judge-intel/profile/{id} is admin-only."""
        response = client.delete("/api/v1/judge-intel/profile/123", headers=non_admin_headers)
        assert response.status_code == 403

    def test_profile_not_built_is_404(self, client, auth_headers):
        with patch(
            "app.routers.judge_intel.judge_intel.get_judge_profile",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.get("/api/v1/judge-intel/profile/123", headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1", "order=name"])
    def test_opinion_query_is_bounded(self, client, auth_headers, query):
        response = client.get(
            f"/api/v1/judge-intel/profile/123/opinions?{query}", headers=auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("limit", [0, 1001])
    def test_search_limit_is_bounded(self, client, auth_headers, limit):
        response = client.get(
            "/api/v1/judge-intel/search",
            params={"q": "Smith", "limit": limit},
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.parametrize(
        ("path", "service_method"),
        [
            ("/profile/4821", "get_judge_profile"),
            ("/profile/4821/stats", "get_statistics"),
        ],
    )
    def test_errors_log_the_judge_id(self, client, auth_headers, caplog, path, service_method):
        """The failure log must name the judge, not the literal text "{judge_id}"."""
        from app.routers import judge_intel as router_module

        with (
            patch.object(
                router_module.judge_intel,
                service_method,
                AsyncMock(side_effect=ValueError("upstream exploded")),
            ),
            caplog.at_level("ERROR"),
        ):
            response = client.get(f"/api/v1/judge-intel{path}", headers=auth_headers)

        assert response.status_code >= 500
        assert "upstream exploded" not in response.text
        logged = " ".join(r.getMessage() for r in caplog.records)
        assert "for judge 4821" in logged
        assert "{judge_id}" not in logged
