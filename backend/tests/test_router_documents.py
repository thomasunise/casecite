"""
Integration tests for the Documents router (/documents).
"""

from unittest.mock import AsyncMock, patch

import pytest
from app.services.audit import AuditEventType
from app.services.documents import document_service
from app.utils.http_headers import content_disposition

from tests.helpers import headers, make_user, register_document

pytestmark = pytest.mark.usefixtures("no_rate_limit")


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
        """GET /documents without auth returns 401."""
        response = client.get("/api/v1/documents")
        assert response.status_code == 401

    @pytest.mark.parametrize("query", ["limit=0", "limit=501", "offset=-1"])
    def test_list_pagination_is_bounded(self, client, auth_headers, query):
        response = client.get(f"/api/v1/documents?{query}", headers=auth_headers)
        assert response.status_code == 422

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

    def test_delete_that_cannot_clean_the_index_says_so(self, client, auth_headers, audit_events):
        """A failed index cleanup leaves the document in place and reports it."""
        from app.services.documents import DocumentDeletionError

        with patch(
            "app.services.documents.document_service.delete_document",
            new_callable=AsyncMock,
            side_effect=DocumentDeletionError("vector delete failed for /app/data/chroma"),
        ):
            response = client.delete("/api/v1/documents/doc-1", headers=auth_headers)
        assert response.status_code == 502
        assert "it was not deleted" in response.json()["detail"]
        assert "/app/data" not in response.text
        failures = [
            e
            for e in audit_events
            if (e.get("details") or {}).get("action") == "document_delete_failed"
        ]
        assert len(failures) == 1
        assert failures[0]["success"] is False


class TestDocumentDownload:
    """GET /documents/{id}/file — filenames are user data and may be any Unicode."""

    @pytest.mark.parametrize(
        "filename",
        [
            "Smith – Engagement Letter.pdf",  # en dash
            "Client’s “Final” Agreement.pdf",  # curly quotes
            "契約書.pdf",  # CJK
            'weird";\r\nSet-Cookie: x=1.pdf',  # header injection attempt
        ],
    )
    def test_non_latin1_filename_downloads(self, client, filename, tmp_path, audit_events):
        owner = make_user("dl-owner")
        doc_id = register_document(owner, filename=filename)
        stored = tmp_path / f"{doc_id}.pdf"
        stored.write_bytes(b"%PDF-1.4 fake")
        try:
            with (
                patch.object(document_service, "_get_user_upload_dir", return_value=str(tmp_path)),
                patch.object(
                    document_service, "read_file", AsyncMock(return_value=b"%PDF-1.4 fake")
                ),
            ):
                response = client.get(f"/api/v1/documents/{doc_id}/file", headers=headers(owner))
        finally:
            document_service.documents.pop(doc_id, None)

        assert response.status_code == 200
        assert response.content == b"%PDF-1.4 fake"
        disposition = response.headers["content-disposition"]
        assert disposition.startswith("inline; filename=")
        assert "filename*=UTF-8''" in disposition
        assert "\r" not in disposition and "\n" not in disposition
        assert "set-cookie" not in {k.lower() for k in response.headers}
        assert [e["event_type"] for e in audit_events] == [AuditEventType.DOCUMENT_DOWNLOAD]


class TestContentDispositionHelper:
    def test_ascii_name_round_trips(self):
        assert content_disposition("attachment", "report.pdf") == (
            "attachment; filename=\"report.pdf\"; filename*=UTF-8''report.pdf"
        )

    def test_unicode_name_is_latin1_encodable_and_rfc5987_encoded(self):
        value = content_disposition("inline", "Smith – Letter “v2”.pdf")
        value.encode("latin-1")  # what Starlette does; must not raise
        assert 'filename="Smith _ Letter _v2_.pdf"' in value
        assert "filename*=UTF-8''Smith%20%E2%80%93%20Letter%20%E2%80%9Cv2%E2%80%9D.pdf" in value

    def test_quotes_and_control_characters_cannot_break_the_header(self):
        value = content_disposition("attachment", 'a"b\r\nX-Evil: 1;c\\d.pdf')
        assert "\r" not in value and "\n" not in value
        assert value.count('"') == 2  # only the two delimiting quotes
        assert 'filename="a_bX-Evil: 1_c_d.pdf"' in value

    def test_empty_name_falls_back(self):
        assert 'filename="download"' in content_disposition("attachment", "")


class TestDocumentAuditTrail:
    def test_direct_upload_is_audited(self, client, audit_events):
        from datetime import UTC, datetime

        from app.models.enums import DocumentStatus
        from app.models.schemas import ConnectorType, Document

        owner = make_user("up-owner")
        doc = Document(
            id="doc-uploaded-1",
            user_id=owner.id,
            filename="notes.txt",
            content_type="text/plain",
            size=11,
            source=ConnectorType.LOCAL,
            status=DocumentStatus.INDEXED,
            created_at=datetime.now(UTC),
        )
        with patch.object(document_service, "upload_and_index", AsyncMock(return_value=doc)):
            response = client.post(
                "/api/v1/documents",
                files={"file": ("Client Matter Notes.txt", b"hello world", "text/plain")},
                headers=headers(owner),
            )
        assert response.status_code == 200, response.text

        uploads = [e for e in audit_events if e["event_type"] == AuditEventType.DOCUMENT_UPLOAD]
        assert len(uploads) == 1
        assert uploads[0]["resource_id"] == "doc-uploaded-1"
        assert uploads[0]["user_id"] == owner.id
        assert uploads[0]["details"]["size"] == 11
        # The (client-identifying) filename is not written to the audit trail.
        assert "Client Matter Notes" not in str(uploads[0])

    def test_failed_upload_is_not_audited_as_an_upload(self, client, audit_events):
        owner = make_user("up-owner")
        with patch.object(
            document_service, "upload_and_index", AsyncMock(side_effect=OSError("disk full"))
        ):
            response = client.post(
                "/api/v1/documents",
                files={"file": ("notes.txt", b"hello world", "text/plain")},
                headers=headers(owner),
            )
        assert response.status_code == 500
        assert not [e for e in audit_events if e["event_type"] == AuditEventType.DOCUMENT_UPLOAD]

    def test_move_and_folder_delete_are_audited(self, client, audit_events):
        owner = make_user("mv-owner")
        doc_id = register_document(owner)
        try:
            with (
                patch.object(document_service, "move_document", return_value=True),
                patch.object(document_service, "delete_folder"),
                patch.object(document_service, "list_folders", return_value=[]),
            ):
                moved = client.post(
                    f"/api/v1/documents/{doc_id}/move",
                    json={"folder_path": "/Clients/Smith/"},
                    headers=headers(owner),
                )
                deleted = client.delete(
                    "/api/v1/documents/folders?path=/Clients/Smith/", headers=headers(owner)
                )
        finally:
            document_service.documents.pop(doc_id, None)

        assert moved.status_code == 200
        assert deleted.status_code == 200
        actions = [e["details"]["action"] for e in audit_events]
        assert actions == ["document_moved", "folder_deleted"]
        assert audit_events[0]["resource_id"] == doc_id
        assert "Smith" not in str(audit_events)  # folder names are client-identifying
