"""
Integration tests for the Documents router (/documents).
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import AsyncMock, patch


class TestDocumentsRouter:
    """Tests for /documents endpoints."""

    def test_list_documents_with_auth(self, client, auth_headers):
        """GET /documents with auth returns document list."""
        with patch(
            "app.services.documents.document_service.list_documents",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = client.get("/api/v1/documents", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert "documents" in data
            assert "count" in data

    def test_list_documents_no_auth(self, client):
        """GET /documents without auth returns 401 or 403."""
        response = client.get("/api/v1/documents")
        assert response.status_code in [401, 403]

    def test_get_document_tree_with_auth(self, client, auth_headers):
        """GET /documents/tree with auth returns tree structure."""
        mock_tree = {"tree": [], "total_documents": 0, "total_folders": 0, "sources": []}
        with patch(
            "app.services.documents.document_service.get_document_tree",
            new_callable=AsyncMock,
            return_value=mock_tree,
        ):
            response = client.get("/api/v1/documents/tree", headers=auth_headers)
            assert response.status_code == 200

    def test_get_single_document_not_found(self, client, auth_headers):
        """GET /documents/{id} for nonexistent doc returns 404."""
        with patch(
            "app.services.documents.document_service.get_document",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.get("/api/v1/documents/nonexistent-id", headers=auth_headers)
            assert response.status_code == 404

    def test_delete_document_not_found(self, client, auth_headers):
        """DELETE /documents/{id} for nonexistent doc returns 404."""
        with patch(
            "app.services.documents.document_service.delete_document",
            new_callable=AsyncMock,
            return_value=False,
        ):
            response = client.delete("/api/v1/documents/nonexistent-id", headers=auth_headers)
            assert response.status_code == 404
