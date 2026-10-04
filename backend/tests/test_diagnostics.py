"""
Unit tests for the Diagnostics service.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.schemas import DocumentStatus


def _doc(filename: str, status=DocumentStatus.INDEXED, error: str | None = None) -> MagicMock:
    doc = MagicMock()
    doc.filename = filename
    doc.status = status
    doc.metadata = {"error": error} if error else {}
    return doc


async def _run(docs: dict, reindex):
    """Run reindex_user_documents with a mocked document service."""
    doc_service = MagicMock()
    doc_service._get_user_documents.return_value = docs
    doc_service.reindex_document = AsyncMock(side_effect=reindex)
    embed_service = MagicMock()
    embed_service.model = "voyage-law-2"

    with (
        patch("app.services.documents.document_service", doc_service),
        patch("app.services.diagnostics.embedding_service", embed_service),
        patch("app.services.user_keys.UserAPIKeys.for_user", return_value="user-keys"),
    ):
        from app.services.diagnostics import reindex_user_documents

        return await reindex_user_documents("user-1"), doc_service


class TestDiagnosticsService:
    """Tests for diagnostics module functions."""

    # ------------------------------------------------------------------ #
    # reindex_user_documents
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_reindex_user_documents_success(self):
        """Every document goes through the one re-index path, with the user's keys."""
        doc = _doc("contract.pdf")

        result, doc_service = await _run({"doc-1": doc}, reindex=lambda *a: doc)

        assert result["status"] == "completed"
        assert result["reindexed"] == 1
        assert result["errors"] == []
        assert result["embedding_model"] == "voyage-law-2"
        # reindex_document keeps the matter tag, folder and metadata; the
        # service must not delete vectors or re-index by hand around it.
        doc_service.reindex_document.assert_awaited_once_with("doc-1", "user-1", "user-keys")
        doc_service._save_index.assert_called_once()

    @pytest.mark.asyncio
    async def test_document_that_failed_to_reembed_is_reported_not_counted(self):
        """A document the re-index marked FAILED must not be counted as reindexed."""
        failed = _doc(
            "contract.pdf", DocumentStatus.FAILED, "Re-indexing failed: provider unavailable"
        )

        result, _ = await _run({"doc-1": failed}, reindex=lambda *a: failed)

        assert result["reindexed"] == 0
        assert result["errors"] == ["contract.pdf: Re-indexing failed: provider unavailable"]

    @pytest.mark.asyncio
    async def test_one_failure_does_not_stop_the_rest(self):
        good = _doc("good.pdf")

        class ProviderDown(Exception):
            pass

        def reindex(doc_id, user_id, user_keys):
            if doc_id == "doc-bad":
                raise ProviderDown("upstream 503")
            return good

        result, _ = await _run({"doc-bad": _doc("bad.pdf"), "doc-good": good}, reindex=reindex)

        assert result["reindexed"] == 1
        assert result["errors"] == ["bad.pdf: upstream 503"]

    @pytest.mark.asyncio
    async def test_reindex_user_documents_file_not_found(self):
        """Should report error when file is missing on disk."""

        def reindex(*args):
            raise FileNotFoundError("the stored file is missing")

        result, _ = await _run({"doc-1": _doc("missing.pdf")}, reindex=reindex)

        assert result["reindexed"] == 0
        assert len(result["errors"]) == 1
        assert "not found" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_reindex_user_documents_no_text(self):
        """Should report error when no text can be extracted."""

        def reindex(*args):
            raise ValueError("no text could be extracted")

        result, _ = await _run({"doc-1": _doc("empty.pdf")}, reindex=reindex)

        assert result["reindexed"] == 0
        assert len(result["errors"]) == 1
        assert "no text" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_document_that_vanished_is_reported(self):
        result, _ = await _run({"doc-1": _doc("gone.pdf")}, reindex=lambda *a: None)

        assert result["reindexed"] == 0
        assert result["errors"] == ["gone.pdf: document not found"]
