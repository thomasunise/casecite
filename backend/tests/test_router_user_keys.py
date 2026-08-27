"""
Integration tests for the UserKeysRouter (/user/keys).
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _bypass_session_validation():
    """Bypass session validation so auth_headers work in tests."""
    with patch("app.middleware.security.session_manager.validate_session", return_value=True):
        yield


class TestUserKeysRouter:
    """Tests for /api/v1/user/keys endpoints."""

    # ==================== Save Key ====================

    def test_save_key_no_auth(self, client):
        """Saving a key requires authentication."""
        resp = client.post(
            "/api/v1/user/keys/save",
            json={
                "key_type": "openai",
                "api_key": "sk-test1234567890abcdef",  # gitleaks:allow - fake fixture
            },
        )
        assert resp.status_code in (401, 403)

    def test_save_key_with_auth(self, client, auth_headers):
        """Save an API key."""
        with (
            patch("app.routers.user_keys.get_user_keys", return_value={}),
            patch("app.routers.user_keys.save_user_keys") as mock_save,
            patch(
                "app.routers.user_keys.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            resp = client.post(
                "/api/v1/user/keys/save",
                json={
                    "key_type": "openai",
                    "api_key": "sk-test1234567890abcdef",  # gitleaks:allow - fake fixture
                },
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "saved"
            assert data["key_type"] == "openai"
            mock_save.assert_called_once()

    def test_save_key_invalid_type(self, client, auth_headers):
        """Save fails with invalid key type."""
        resp = client.post(
            "/api/v1/user/keys/save",
            json={
                "key_type": "invalid_provider",
                "api_key": "sk-test1234567890",  # gitleaks:allow - fake fixture
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "Invalid key type" in resp.json()["detail"]

    def test_save_key_too_short(self, client, auth_headers):
        """Save fails with a key that's too short."""
        resp = client.post(
            "/api/v1/user/keys/save",
            json={"key_type": "openai", "api_key": "short"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "Invalid API key format" in resp.json()["detail"]

    # ==================== Key Status ====================

    def test_key_status_no_auth(self, client):
        """Key status requires authentication."""
        resp = client.get("/api/v1/user/keys/status")
        assert resp.status_code in (401, 403)

    def test_key_status_with_auth(self, client, auth_headers):
        """Get status of configured keys."""
        with patch(
            "app.routers.user_keys.get_user_keys",
            return_value={
                "openai": "sk-real-key-here-1234567890",
                "anthropic": None,
                "_last_updated": "2026-01-01T00:00:00",
            },
        ):
            resp = client.get("/api/v1/user/keys/status", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["openai_configured"] is True
            assert data["anthropic_configured"] is False
            assert data["last_updated"] == "2026-01-01T00:00:00"

    def test_key_status_empty(self, client, auth_headers):
        """Key status when no keys are configured."""
        with patch("app.routers.user_keys.get_user_keys", return_value={}):
            resp = client.get("/api/v1/user/keys/status", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["openai_configured"] is False
            assert data["anthropic_configured"] is False
            assert data["google_configured"] is False
            assert data["voyage_configured"] is False
            assert data["cohere_configured"] is False

    # ==================== Masked Keys ====================

    def test_get_masked_keys(self, client, auth_headers):
        """Get masked versions of configured keys."""
        with patch(
            "app.routers.user_keys.get_user_keys",
            return_value={
                "openai": "sk-1234567890abcdefghijklmnop",  # gitleaks:allow - fake fixture
                "anthropic": None,
            },
        ):
            resp = client.get("/api/v1/user/keys/masked", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            # Should show first 4 and last 4 chars with dots in between
            assert data["openai"] is not None
            assert data["openai"].startswith("sk-1")
            assert data["openai"].endswith("mnop")
            assert "\u2022" in data["openai"]
            # Unconfigured key should be None
            assert data["anthropic"] is None

    def test_get_masked_keys_no_auth(self, client):
        """Masked keys require authentication."""
        resp = client.get("/api/v1/user/keys/masked")
        assert resp.status_code in (401, 403)
