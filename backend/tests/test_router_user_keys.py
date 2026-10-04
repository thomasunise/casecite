"""
Integration tests for the UserKeysRouter (/user/keys).
"""

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.usefixtures("no_rate_limit")


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

    # ==================== Delete Key ====================

    def test_delete_key_no_auth(self, client):
        assert client.delete("/api/v1/user/keys/openai").status_code == 401

    def test_delete_key_invalid_type(self, client, auth_headers):
        resp = client.delete("/api/v1/user/keys/not-a-provider", headers=auth_headers)
        assert resp.status_code == 400

    def test_delete_key_not_stored(self, client, auth_headers):
        with patch("app.routers.user_keys.get_user_keys", return_value={}):
            resp = client.delete("/api/v1/user/keys/openai", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_one_key_keeps_the_others(self, client, auth_headers, audit_events):
        stored = {
            "openai": "sk-test1234567890abcdef",  # gitleaks:allow - fake fixture
            "anthropic": "sk-ant-test1234567890",  # gitleaks:allow - fake fixture
            "_last_updated": "2026-01-01T00:00:00",
        }
        with (
            patch("app.routers.user_keys.get_user_keys", return_value=dict(stored)),
            patch("app.routers.user_keys.save_user_keys") as mock_save,
            patch("app.routers.user_keys.delete_user_keys") as mock_delete_all,
        ):
            resp = client.delete("/api/v1/user/keys/openai", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted", "key_type": "openai"}
        saved = mock_save.call_args.args[1]
        assert "openai" not in saved
        assert saved["anthropic"] == stored["anthropic"]
        mock_delete_all.assert_not_called()

        assert len(audit_events) == 1
        assert audit_events[0]["event_type"].value == "apikey.deleted"
        assert audit_events[0]["resource_id"] == "openai"
        assert "sk-test" not in str(audit_events[0])

    def test_delete_last_key_drops_the_users_record(self, client, auth_headers, audit_events):
        stored = {"openai": "sk-test1234567890abcdef"}  # gitleaks:allow - fake fixture
        with (
            patch("app.routers.user_keys.get_user_keys", return_value=dict(stored)),
            patch("app.routers.user_keys.save_user_keys") as mock_save,
            patch("app.routers.user_keys.delete_user_keys") as mock_delete_all,
        ):
            resp = client.delete("/api/v1/user/keys/openai", headers=auth_headers)

        assert resp.status_code == 200
        mock_delete_all.assert_called_once_with("test-user-123")
        mock_save.assert_not_called()

    def test_delete_reports_storage_failure(self, client, auth_headers, audit_events):
        """A key that could not be removed from disk must not be reported deleted."""
        stored = {"openai": "sk-test1234567890abcdef"}  # gitleaks:allow - fake fixture
        with (
            patch("app.routers.user_keys.get_user_keys", return_value=dict(stored)),
            patch(
                "app.routers.user_keys.delete_user_keys",
                side_effect=RuntimeError("Key storage unavailable"),
            ),
        ):
            resp = client.delete("/api/v1/user/keys/openai", headers=auth_headers)
        assert resp.status_code == 503
        assert audit_events == []

    def test_save_then_delete_round_trip(self, client, auth_headers, tmp_path):
        """End to end against the real encrypted store (in a temp file)."""
        with (
            patch("app.services.key_storage._KEYS_FILE", tmp_path / ".user_keys.json"),
            patch("app.services.key_storage._DATA_DIR", tmp_path),
            patch("app.services.key_storage.get_redis", return_value=None),
        ):
            saved = client.post(
                "/api/v1/user/keys/save",
                json={
                    "key_type": "openai",
                    "api_key": "sk-test1234567890abcdef",  # gitleaks:allow - fake fixture
                },
                headers=auth_headers,
            )
            assert saved.status_code == 200
            status = client.get("/api/v1/user/keys/status", headers=auth_headers).json()
            assert status["openai_configured"] is True

            deleted = client.delete("/api/v1/user/keys/openai", headers=auth_headers)
            assert deleted.status_code == 200
            status = client.get("/api/v1/user/keys/status", headers=auth_headers).json()
            assert status["openai_configured"] is False
            # The ciphertext is gone from disk, not just hidden.
            assert (tmp_path / ".user_keys.json").read_text() == "{}"

    def test_save_key_rejects_oversized_key(self, client, auth_headers):
        resp = client.post(
            "/api/v1/user/keys/save",
            json={"key_type": "openai", "api_key": "sk-" + "a" * 600},
            headers=auth_headers,
        )
        assert resp.status_code == 422
