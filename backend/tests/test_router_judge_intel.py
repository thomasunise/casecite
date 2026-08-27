"""
Integration tests for Judge Intel router (/api/v1/judge-intel).
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"


class TestJudgeIntelRouter:
    """Tests for /api/v1/judge-intel endpoints."""

    def test_search_no_auth(self, client):
        """GET /api/v1/judge-intel/search without auth returns 401/402/403."""
        response = client.get("/api/v1/judge-intel/search", params={"q": "Smith"})
        assert response.status_code in [401, 402, 403]

    def test_delete_profile_requires_admin(self, client, non_admin_headers):
        """DELETE /judge-intel/profile/{id} is admin-only."""
        response = client.delete("/api/v1/judge-intel/profile/123", headers=non_admin_headers)
        assert response.status_code == 403
