"""
Integration tests for the PickersRouter (/pickers).
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


class TestPickersRouter:
    """Tests for /api/v1/pickers endpoints."""

    # ==================== Config ====================

    def test_get_picker_config_no_auth(self, client):
        """Picker config requires authentication."""
        resp = client.get("/api/v1/pickers/config")
        assert resp.status_code in (401, 403)

    def test_get_picker_config_with_auth(self, client, auth_headers):
        """Get picker configuration for frontend."""
        resp = client.get("/api/v1/pickers/config", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # In test mode, settings won't have provider keys configured
        assert "google_enabled" in data
        assert "microsoft_enabled" in data
        assert "box_enabled" in data
        assert "dropbox_enabled" in data
        # API key should never be exposed
        assert data.get("google_api_key") is None

    # ==================== Google Picker Import ====================

    def test_google_import_no_auth(self, client):
        """Google import requires authentication."""
        resp = client.post(
            "/api/v1/pickers/google/import",
            json=[
                {
                    "id": "file-1",
                    "name": "document.pdf",
                    "mimeType": "application/pdf",
                    "oauthToken": "ya29.test-token",
                }
            ],
        )
        assert resp.status_code in (401, 403)

    def test_google_import_with_auth(self, client, auth_headers):
        """Import files from Google Picker."""
        with (
            patch(
                "app.routers.pickers.safe_download",
                new_callable=AsyncMock,
            ) as mock_download,
            patch(
                "app.routers.pickers.document_service.upload_and_index",
                new_callable=AsyncMock,
            ) as _mock_upload,
            patch(
                "app.routers.pickers.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            mock_download.return_value = b"%PDF-1.4 fake pdf content"

            resp = client.post(
                "/api/v1/pickers/google/import",
                json=[
                    {
                        "id": "file-1",
                        "name": "document.pdf",
                        "mimeType": "application/pdf",
                        "oauthToken": "ya29.test-token",
                    }
                ],
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["imported"] == 1
            assert data["failed"] == 0

    # ==================== Box Picker Token ====================

    def test_box_token_no_auth(self, client):
        """Box picker token requires authentication."""
        resp = client.get("/api/v1/pickers/box/token")
        assert resp.status_code in (401, 403)

    def test_box_token_not_connected(self, client, auth_headers):
        """409 when the Box connector has no stored credentials."""
        with (
            patch(
                "app.services.connectors.box.BoxConnector.is_configured",
                new_callable=lambda: property(lambda self: True),
            ),
            patch(
                "app.services.connectors.box.BoxConnector.is_connected",
                new_callable=lambda: property(lambda self: False),
            ),
        ):
            resp = client.get("/api/v1/pickers/box/token", headers=auth_headers)
            assert resp.status_code == 409

    def test_box_token_downscoped(self, client, auth_headers):
        """Returns the downscoped token when Box is connected."""
        with (
            patch(
                "app.services.connectors.box.BoxConnector.is_configured",
                new_callable=lambda: property(lambda self: True),
            ),
            patch(
                "app.services.connectors.box.BoxConnector.is_connected",
                new_callable=lambda: property(lambda self: True),
            ),
            patch(
                "app.services.connectors.box.BoxConnector.get_downscoped_token",
                new_callable=AsyncMock,
                return_value={"access_token": "downscoped-token", "expires_in": 3600},
            ),
        ):
            resp = client.get("/api/v1/pickers/box/token", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["access_token"] == "downscoped-token"
            assert data["expires_in"] == 3600

    # ==================== OneDrive Picker Import ====================

    def test_onedrive_import_no_auth(self, client):
        """OneDrive import requires authentication."""
        resp = client.post(
            "/api/v1/pickers/microsoft/import",
            json=[
                {
                    "id": "file-2",
                    "name": "brief.docx",
                    "accessToken": "eyJ0...",
                }
            ],
        )
        assert resp.status_code in (401, 403)

    def test_onedrive_import_with_auth(self, client, auth_headers):
        """Import files from OneDrive Picker."""
        with (
            patch(
                "app.routers.pickers.safe_download",
                new_callable=AsyncMock,
            ) as mock_download,
            patch(
                "app.routers.pickers.document_service.upload_and_index",
                new_callable=AsyncMock,
            ),
            patch(
                "app.routers.pickers.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            import io as _io
            import zipfile

            _buf = _io.BytesIO()
            with zipfile.ZipFile(_buf, "w") as _z:
                _z.writestr("[Content_Types].xml", "<Types/>")
            # Real zip container: libmagic (present in CI) reports octet-stream
            # for a bare PK header, which would fail content validation.
            mock_download.return_value = _buf.getvalue()

            resp = client.post(
                "/api/v1/pickers/microsoft/import",
                json=[
                    {
                        "id": "file-2",
                        "name": "brief.docx",
                        "accessToken": "eyJ0...",
                        "downloadUrl": "https://download.example.com/file",
                    }
                ],
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["imported"] == 1

    # ==================== Box Picker Import ====================

    def test_box_import_no_auth(self, client):
        """Box import requires authentication."""
        resp = client.post(
            "/api/v1/pickers/box/import",
            json=[
                {
                    "id": "file-3",
                    "name": "contract.pdf",
                    "accessToken": "box-token",
                }
            ],
        )
        assert resp.status_code in (401, 403)

    def test_box_import_with_auth(self, client, auth_headers):
        """Import files from Box Picker."""
        with (
            patch(
                "app.routers.pickers.safe_download",
                new_callable=AsyncMock,
            ) as mock_download,
            patch(
                "app.routers.pickers.document_service.upload_and_index",
                new_callable=AsyncMock,
            ),
            patch(
                "app.routers.pickers.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            mock_download.return_value = b"%PDF-1.4 fake pdf content"

            resp = client.post(
                "/api/v1/pickers/box/import",
                json=[
                    {
                        "id": "file-3",
                        "name": "contract.pdf",
                        "accessToken": "box-token",
                    }
                ],
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["imported"] == 1

    # ==================== Dropbox Chooser Import ====================

    def test_dropbox_import_no_auth(self, client):
        """Dropbox import requires authentication."""
        resp = client.post(
            "/api/v1/pickers/dropbox/import",
            json=[
                {
                    "name": "filing.pdf",
                    "link": "https://dl.dropboxusercontent.com/1/view/abc123/filing.pdf",
                }
            ],
        )
        assert resp.status_code in (401, 403)

    def test_dropbox_import_with_auth(self, client, auth_headers):
        """Import files from Dropbox Chooser."""
        with (
            patch(
                "app.routers.pickers.safe_download",
                new_callable=AsyncMock,
            ) as mock_download,
            patch(
                "app.routers.pickers.document_service.upload_and_index",
                new_callable=AsyncMock,
            ),
            patch(
                "app.routers.pickers.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            mock_download.return_value = b"%PDF-1.4 fake pdf content"

            resp = client.post(
                "/api/v1/pickers/dropbox/import",
                json=[
                    {
                        "name": "filing.pdf",
                        "link": "https://dl.dropboxusercontent.com/1/view/abc123/filing.pdf",
                    }
                ],
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["imported"] == 1

    def test_dropbox_import_empty_list(self, client, auth_headers):
        """Import with empty file list."""
        with patch(
            "app.routers.pickers.audit_service.log_event",
            new_callable=AsyncMock,
        ):
            resp = client.post(
                "/api/v1/pickers/dropbox/import",
                json=[],
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["imported"] == 0
            assert data["failed"] == 0
