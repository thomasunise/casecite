"""
Unit tests for the Diagnostics service.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDiagnosticsService:
    """Tests for diagnostics module functions."""

    # ------------------------------------------------------------------ #
    # reindex_user_documents
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_reindex_user_documents_success(self):
        """Should reindex all documents and return summary."""
        mock_doc = MagicMock()
        mock_doc.filename = "contract.pdf"
        mock_doc.content_type = "application/pdf"
        mock_doc.source = MagicMock()
        mock_doc.source.value = "local"
        mock_doc.chunk_count = 0

        mock_doc_service = MagicMock()
        mock_doc_service._get_user_documents.return_value = {"doc-1": mock_doc}
        mock_doc_service._get_user_upload_dir.return_value = "/uploads/user-1"
        mock_doc_service.extract_text = AsyncMock(return_value="Contract text content here.")
        mock_doc_service._classify_document.return_value = "contract"
        mock_doc_service._save_index = MagicMock()

        mock_rag_service = AsyncMock()
        mock_rag_service.delete_document = AsyncMock()
        mock_rag_service.index_document = AsyncMock(return_value=5)

        mock_embed_service = MagicMock()
        mock_embed_service.model = "voyage-law-2"

        with (
            patch("app.services.documents.document_service", mock_doc_service),
            patch("app.services.rag.rag_service", mock_rag_service),
            patch("app.services.diagnostics.embedding_service", mock_embed_service),
            patch("os.path.exists", return_value=True),
        ):
            from app.services.diagnostics import reindex_user_documents

            result = await reindex_user_documents("user-1")

        assert result["status"] == "completed"
        assert result["reindexed"] == 1
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_reindex_user_documents_file_not_found(self):
        """Should report error when file is missing on disk."""
        mock_doc = MagicMock()
        mock_doc.filename = "missing.pdf"
        mock_doc.content_type = "application/pdf"
        mock_doc.source = MagicMock()
        mock_doc.source.value = "local"

        mock_doc_service = MagicMock()
        mock_doc_service._get_user_documents.return_value = {"doc-1": mock_doc}
        mock_doc_service._get_user_upload_dir.return_value = "/uploads/user-1"
        mock_doc_service._save_index = MagicMock()

        mock_embed_service = MagicMock()
        mock_embed_service.model = "voyage-law-2"

        with (
            patch("app.services.documents.document_service", mock_doc_service),
            patch("app.services.diagnostics.embedding_service", mock_embed_service),
            patch("os.path.exists", return_value=False),
        ):
            from app.services.diagnostics import reindex_user_documents

            result = await reindex_user_documents("user-1")

        assert result["reindexed"] == 0
        assert len(result["errors"]) == 1
        assert "not found" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_reindex_user_documents_no_text(self):
        """Should report error when no text can be extracted."""
        mock_doc = MagicMock()
        mock_doc.filename = "empty.pdf"
        mock_doc.content_type = "application/pdf"
        mock_doc.source = MagicMock()
        mock_doc.source.value = "local"

        mock_doc_service = MagicMock()
        mock_doc_service._get_user_documents.return_value = {"doc-1": mock_doc}
        mock_doc_service._get_user_upload_dir.return_value = "/uploads/user-1"
        mock_doc_service.extract_text = AsyncMock(return_value="   ")
        mock_doc_service._save_index = MagicMock()

        mock_embed_service = MagicMock()
        mock_embed_service.model = "voyage-law-2"

        with (
            patch("app.services.documents.document_service", mock_doc_service),
            patch("app.services.diagnostics.embedding_service", mock_embed_service),
            patch("os.path.exists", return_value=True),
        ):
            from app.services.diagnostics import reindex_user_documents

            result = await reindex_user_documents("user-1")

        assert result["reindexed"] == 0
        assert len(result["errors"]) == 1
        assert "no text" in result["errors"][0]
