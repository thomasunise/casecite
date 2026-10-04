"""
Unit tests for the UserSettings service.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import json
from unittest.mock import patch

from app.models.schemas import RAGSettings
from app.services.user_settings import (
    SETTINGS_DIR,
    _get_user_settings_path,
    load_user_settings,
    save_user_settings,
)

# =============================================================================
# _get_user_settings_path Tests
# =============================================================================


class TestGetUserSettingsPath:
    """Tests for _get_user_settings_path."""

    def test_returns_file_path_with_sanitized_id(self):
        path = _get_user_settings_path("user-123")
        assert path.endswith("rag_settings_user-123.json")
        assert SETTINGS_DIR in path

    def test_sanitizes_special_characters(self):
        path = _get_user_settings_path("../../etc/passwd")
        # Only alphanumeric, hyphens, and underscores should remain
        filename = os.path.basename(path)
        assert ".." not in filename
        assert "/" not in filename
        assert "passwd" in filename  # alphanumeric chars preserved

    def test_sanitizes_spaces_and_symbols(self):
        path = _get_user_settings_path("user@email.com")
        filename = os.path.basename(path)
        # @ and . should be stripped
        assert "@" not in filename
        assert ".com" not in filename.replace(".json", "")

    def test_empty_user_id(self):
        path = _get_user_settings_path("")
        assert path.endswith("rag_settings_.json")

    def test_uuid_style_user_id(self):
        uid = "550e8400-e29b-41d4-a716-446655440000"
        path = _get_user_settings_path(uid)
        # Hyphens should be preserved
        assert uid in path


# =============================================================================
# load_user_settings Tests
# =============================================================================


class TestLoadUserSettings:
    """Tests for load_user_settings."""

    def test_returns_defaults_when_no_file(self, tmp_path):
        with patch(
            "app.services.user_settings._get_user_settings_path",
            return_value=str(tmp_path / "nonexistent.json"),
        ):
            settings = load_user_settings("user-1")
            assert isinstance(settings, RAGSettings)
            assert settings.vector_db == "chroma"
            assert settings.chunk_size == 512

    def test_loads_from_file(self, tmp_path):
        settings_data = {
            "vector_db": "chroma",
            "chunk_size": 1024,
            "top_k": 20,
            "temperature": 0.3,
        }
        settings_file = tmp_path / "rag_settings_user-1.json"
        settings_file.write_text(json.dumps(settings_data))

        with patch(
            "app.services.user_settings._get_user_settings_path",
            return_value=str(settings_file),
        ):
            settings = load_user_settings("user-1")
            assert settings.chunk_size == 1024
            assert settings.top_k == 20
            assert settings.temperature == 0.3

    def test_returns_defaults_on_invalid_json(self, tmp_path):
        settings_file = tmp_path / "rag_settings_user-bad.json"
        settings_file.write_text("{not valid json}")

        with patch(
            "app.services.user_settings._get_user_settings_path",
            return_value=str(settings_file),
        ):
            settings = load_user_settings("user-bad")
            assert isinstance(settings, RAGSettings)
            # Should return defaults
            assert settings.chunk_size == 512

    def test_returns_defaults_on_permission_error(self, tmp_path):
        with (
            patch(
                "app.services.user_settings._get_user_settings_path",
                return_value=str(tmp_path / "rag_settings_user-1.json"),
            ),
            patch("os.path.exists", return_value=True),
            patch("builtins.open", side_effect=OSError("Permission denied")),
        ):
            settings = load_user_settings("user-1")
            assert isinstance(settings, RAGSettings)


# =============================================================================
# save_user_settings Tests
# =============================================================================


class TestSaveUserSettings:
    """Tests for save_user_settings."""

    def test_saves_settings_to_file(self, tmp_path):
        settings_file = tmp_path / "rag_settings_user-1.json"

        with patch(
            "app.services.user_settings._get_user_settings_path",
            return_value=str(settings_file),
        ):
            rag_settings = RAGSettings(chunk_size=1024, top_k=15, temperature=0.5)
            save_user_settings("user-1", rag_settings)

            assert settings_file.exists()
            data = json.loads(settings_file.read_text())
            assert data["chunk_size"] == 1024
            assert data["top_k"] == 15
            assert data["temperature"] == 0.5

    def test_overwrites_existing_file(self, tmp_path):
        settings_file = tmp_path / "rag_settings_user-1.json"
        settings_file.write_text(json.dumps({"chunk_size": 256}))

        with patch(
            "app.services.user_settings._get_user_settings_path",
            return_value=str(settings_file),
        ):
            rag_settings = RAGSettings(chunk_size=2000)
            save_user_settings("user-1", rag_settings)

            data = json.loads(settings_file.read_text())
            assert data["chunk_size"] == 2000

    def test_creates_directory_if_needed(self, tmp_path):
        nested_dir = tmp_path / "subdir" / "nested"
        settings_file = nested_dir / "rag_settings_user-1.json"

        with patch(
            "app.services.user_settings._get_user_settings_path",
            return_value=str(settings_file),
        ):
            rag_settings = RAGSettings()
            save_user_settings("user-1", rag_settings)

            assert settings_file.exists()

    def test_handles_save_error_gracefully(self, tmp_path):
        with patch(
            "app.services.user_settings._get_user_settings_path",
            return_value="/invalid/path/settings.json",
        ):
            rag_settings = RAGSettings()
            # Should not raise
            save_user_settings("user-1", rag_settings)


# =============================================================================
# Round-trip Tests
# =============================================================================


class TestRoundTrip:
    """Tests for save + load round-trip."""

    def test_save_and_load_preserves_settings(self, tmp_path):
        settings_file = tmp_path / "rag_settings_user-rt.json"

        with patch(
            "app.services.user_settings._get_user_settings_path",
            return_value=str(settings_file),
        ):
            original = RAGSettings(
                vector_db="chroma",
                chunk_size=1000,
                chunk_overlap=200,
                similarity_threshold=0.7,
                top_k=25,
                enable_reranking=False,
                hybrid_search=False,
                temperature=0.5,
                max_tokens=8000,
            )

            save_user_settings("user-rt", original)
            loaded = load_user_settings("user-rt")

            assert loaded.vector_db == original.vector_db
            assert loaded.chunk_size == original.chunk_size
            assert loaded.chunk_overlap == original.chunk_overlap
            assert loaded.similarity_threshold == original.similarity_threshold
            assert loaded.top_k == original.top_k
            assert loaded.enable_reranking == original.enable_reranking
            assert loaded.hybrid_search == original.hybrid_search
            assert loaded.temperature == original.temperature
            assert loaded.max_tokens == original.max_tokens


# =============================================================================
# Module-level Tests
# =============================================================================


class TestModuleLevelConstants:
    """Tests for module-level constants and initialization."""

    def test_settings_dir_exists(self):
        assert os.path.isdir(SETTINGS_DIR)

    def test_settings_dir_is_a_string(self):
        assert isinstance(SETTINGS_DIR, str)
        assert len(SETTINGS_DIR) > 0


class TestSettingsDirectory:
    def test_unwritable_data_dir_fails_loudly_instead_of_using_the_temp_dir(self):
        """Settings hold a firm's playbook; they must never land in a temp dir."""
        import importlib

        import app.services.user_settings as module
        import pytest

        try:
            with (
                patch("os.makedirs", side_effect=PermissionError("read-only volume")),
                pytest.raises(RuntimeError, match="must be writable"),
            ):
                importlib.reload(module)
        finally:
            importlib.reload(module)
