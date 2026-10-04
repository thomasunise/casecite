"""
Tests for API endpoints.
"""

from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_root_endpoint(self, client: TestClient):
        """Test root endpoint returns 200 (serves frontend SPA or JSON info)."""
        response = client.get("/")

        assert response.status_code == 200
        # Root may return HTML (frontend SPA) or JSON (API info) depending on
        # whether frontend/dist/index.html exists.
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            data = response.json()
            assert "name" in data
            assert "status" in data
            assert data["status"] == "running"
        else:
            # Frontend SPA is being served
            assert len(response.content) > 0

    def test_health_endpoint(self, client: TestClient):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "components" in data

    def test_ready_endpoint(self, client: TestClient):
        """Test readiness endpoint."""
        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert "ready" in data


class TestAuthEndpoints:
    """Test authentication endpoints."""

    def test_unauthenticated_request_to_protected_endpoint(self, client: TestClient):
        """Test that protected endpoints require authentication."""
        response = client.get("/api/v1/documents")

        assert response.status_code == 401

    def test_authenticated_request(self, client: TestClient, auth_headers: dict):
        """Test that authenticated requests succeed."""
        response = client.get("/api/v1/documents", headers=auth_headers)

        # Should not return 401 (authentication should pass)
        assert response.status_code != 401


class TestDocumentEndpoints:
    """Test document management endpoints."""

    def test_list_documents_requires_auth(self, client: TestClient):
        """Test that listing documents requires authentication."""
        response = client.get("/api/v1/documents")
        assert response.status_code == 401

    def test_list_documents_authenticated(self, client: TestClient, auth_headers: dict):
        """Test listing documents with authentication."""
        response = client.get("/api/v1/documents", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "count" in data


class TestSettingsEndpoints:
    """Test settings endpoints."""

    def test_get_rag_settings_requires_auth(self, client: TestClient):
        """Test that RAG settings require authentication."""
        response = client.get("/api/v1/settings/rag")
        assert response.status_code == 401

    def test_get_rag_settings_authenticated(self, client: TestClient, auth_headers: dict):
        """Test getting RAG settings with authentication."""
        response = client.get("/api/v1/settings/rag", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "top_k" in data
        assert "similarity_threshold" in data

    def test_clear_index_requires_admin(self, client: TestClient, non_admin_headers: dict):
        """Test that clearing index requires admin role."""
        response = client.post("/api/v1/settings/clear", headers=non_admin_headers)
        assert response.status_code == 403

    def test_reindex_requires_admin(self, client: TestClient, non_admin_headers: dict):
        """Test that reindex requires admin role."""
        response = client.post("/api/v1/settings/reindex", headers=non_admin_headers)
        assert response.status_code == 403


class TestChatEndpoints:
    """Test chat endpoints."""

    def test_chat_requires_auth(self, client: TestClient):
        """Test that chat endpoint requires authentication."""
        response = client.post("/api/v1/chat", json={"query": "What is contract law?"})
        assert response.status_code == 401


class TestConnectorEndpoints:
    """Test connector endpoints."""

    def test_list_connectors_requires_auth(self, client: TestClient):
        """Test that listing connectors requires authentication."""
        response = client.get("/api/v1/connectors")
        assert response.status_code == 401

    def test_list_connectors_authenticated(self, client: TestClient, auth_headers: dict):
        """Test listing connectors with authentication."""
        response = client.get("/api/v1/connectors", headers=auth_headers)
        assert response.status_code == 200


class TestJudgeIntelEndpoints:
    """Test judge intelligence endpoints."""

    def test_search_judges_requires_auth(self, client: TestClient):
        """Test that searching judges requires authentication."""
        response = client.get("/api/v1/judge-intel/search?q=Smith")
        assert response.status_code == 401
