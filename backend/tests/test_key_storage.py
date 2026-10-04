"""
Unit tests for the KeyStorage service.

The store is durable and file-backed (``data/.user_keys.json``): encrypted at
rest, source of truth on disk, with Redis used only as an optional read-through
cache. These tests isolate the on-disk store to a temp file per test.
"""

from unittest.mock import MagicMock, patch

import pytest
from app.services import key_storage
from app.services.key_storage import (
    _CACHE_TTL_SECONDS,
    delete_user_keys,
    get_user_api_key,
    get_user_keys,
    save_user_keys,
)


@pytest.fixture(autouse=True)
def isolated_store(tmp_path):
    """Point the durable key store at a temp file for each test."""
    keys_file = tmp_path / ".user_keys.json"
    with (
        patch.object(key_storage, "_DATA_DIR", tmp_path),
        patch.object(key_storage, "_KEYS_FILE", keys_file),
    ):
        yield keys_file


@pytest.fixture
def mock_no_redis():
    """Ensure Redis is not used for these tests."""
    with patch("app.services.key_storage.get_redis", return_value=None):
        yield


class TestSaveAndGetUserKeys:
    """Tests for save_user_keys and get_user_keys."""

    def test_save_and_retrieve_keys(self, mock_no_redis):
        keys = {"openai": "sk-test123456789", "anthropic": "sk-ant-test123456"}
        save_user_keys("user-1", keys)

        result = get_user_keys("user-1")
        assert result["openai"] == "sk-test123456789"
        assert result["anthropic"] == "sk-ant-test123456"

    def test_get_nonexistent_user_returns_empty(self, mock_no_redis):
        result = get_user_keys("nonexistent-user")
        assert result == {}

    def test_overwrite_existing_keys(self, mock_no_redis):
        save_user_keys("user-1", {"openai": "sk-old-key-1234567"})
        save_user_keys("user-1", {"openai": "sk-new-key-1234567"})

        result = get_user_keys("user-1")
        assert result["openai"] == "sk-new-key-1234567"

    def test_keys_persist_on_disk_as_ciphertext(self, mock_no_redis, isolated_store):
        save_user_keys("user-1", {"openai": "sk-secret-plaintext-1"})

        # File exists and does NOT contain the plaintext key.
        assert isolated_store.exists()
        raw = isolated_store.read_text()
        assert "sk-secret-plaintext-1" not in raw

    def test_keys_survive_process_restart(self, mock_no_redis):
        """A fresh read (no in-memory state) still returns persisted keys."""
        save_user_keys("user-1", {"openai": "sk-durable-12345678"})
        # get_user_keys reads from disk each time — no in-process cache to clear.
        assert get_user_keys("user-1")["openai"] == "sk-durable-12345678"

    def test_multiple_users_isolated(self, mock_no_redis):
        save_user_keys("user-a", {"openai": "sk-user-a-key-1234"})
        save_user_keys("user-b", {"openai": "sk-user-b-key-1234"})

        assert get_user_keys("user-a")["openai"] == "sk-user-a-key-1234"
        assert get_user_keys("user-b")["openai"] == "sk-user-b-key-1234"


class TestDeleteUserKeys:
    """Tests for delete_user_keys."""

    def test_delete_existing_keys(self, mock_no_redis):
        save_user_keys("user-1", {"openai": "sk-test123456789"})
        assert get_user_keys("user-1") != {}

        delete_user_keys("user-1")
        assert get_user_keys("user-1") == {}

    def test_delete_only_targets_one_user(self, mock_no_redis):
        save_user_keys("user-1", {"openai": "sk-keep-this-key-12"})
        save_user_keys("user-2", {"openai": "sk-drop-this-key-12"})

        delete_user_keys("user-2")
        assert get_user_keys("user-1")["openai"] == "sk-keep-this-key-12"
        assert get_user_keys("user-2") == {}

    def test_delete_nonexistent_user_no_error(self, mock_no_redis):
        save_user_keys("user-1", {"openai": "sk-keep-this-key-12"})

        # Should not raise even if user doesn't exist, and must leave others alone.
        delete_user_keys("nonexistent-user")
        assert get_user_keys("nonexistent-user") == {}
        assert get_user_keys("user-1")["openai"] == "sk-keep-this-key-12"

    def test_delete_failure_is_not_swallowed(self, mock_no_redis):
        """If the store cannot be rewritten the key is still on disk — say so."""
        save_user_keys("user-1", {"openai": "sk-keep-this-key-12"})

        with (
            patch("app.services.key_storage._write_store", side_effect=OSError("read-only fs")),
            pytest.raises(RuntimeError, match="Key storage unavailable"),
        ):
            delete_user_keys("user-1")
        assert get_user_keys("user-1")["openai"] == "sk-keep-this-key-12"


class TestGetUserApiKey:
    """Tests for get_user_api_key."""

    def test_returns_specific_key(self, mock_no_redis):
        save_user_keys("user-1", {"openai": "sk-test123456789", "anthropic": "sk-ant-test123456"})

        result = get_user_api_key("user-1", "openai")
        assert result == "sk-test123456789"

    def test_returns_none_for_missing_key_type(self, mock_no_redis):
        save_user_keys("user-1", {"openai": "sk-test123456789"})

        result = get_user_api_key("user-1", "anthropic")
        assert result is None

    def test_returns_none_for_missing_user(self, mock_no_redis):
        result = get_user_api_key("nonexistent", "openai")
        assert result is None


class TestRedisCache:
    """Tests for the optional Redis read-through cache."""

    def test_save_refreshes_cache_with_cache_ttl(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch("app.services.key_storage.get_redis", return_value=mock_redis):
            save_user_keys("user-1", {"openai": "sk-test123456789"})
            mock_redis.setex.assert_called_once()

            call_args = mock_redis.setex.call_args
            assert call_args[0][0] == "user_keys:user-1"
            assert call_args[0][1] == _CACHE_TTL_SECONDS

    def test_delete_evicts_cache(self):
        mock_redis = MagicMock()

        with patch("app.services.key_storage.get_redis", return_value=mock_redis):
            delete_user_keys("user-1")
            mock_redis.delete.assert_called_once_with("user_keys:user-1")

    def test_redis_error_falls_back_to_file(self):
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = OSError("Redis connection lost")
        mock_redis.get.side_effect = OSError("Redis connection lost")

        with patch("app.services.key_storage.get_redis", return_value=mock_redis):
            # Save should still persist to the durable file store.
            save_user_keys("user-2", {"openai": "sk-test123456789"})

            # Get should read back from the file store despite the cache erroring.
            result = get_user_keys("user-2")
            assert result["openai"] == "sk-test123456789"
