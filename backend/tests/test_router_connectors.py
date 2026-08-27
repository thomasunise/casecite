"""
Integration tests for Connectors router (/connectors).
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"


class TestConnectorsRouter:
    """Tests for /connectors endpoints."""

    def test_list_connectors(self, client, auth_headers):
        """GET /connectors returns connector list."""
        response = client.get("/api/v1/connectors", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_list_connectors_no_auth(self, client):
        """GET /connectors without auth returns 401/403."""
        response = client.get("/api/v1/connectors")
        assert response.status_code in [401, 403]

    def test_connector_status(self, client, auth_headers):
        """GET /connectors/{type}/status returns status."""
        response = client.get("/api/v1/connectors/google_drive/status", headers=auth_headers)
        assert response.status_code in [200, 404]

    def test_disconnect_no_auth(self, client):
        """POST /connectors/{type}/disconnect without auth returns 401/403."""
        response = client.post("/api/v1/connectors/google_drive/disconnect")
        assert response.status_code in [401, 403]
