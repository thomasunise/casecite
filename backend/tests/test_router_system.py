"""
Integration tests for the SystemRouter (/, /health, /ready, /metrics).
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _bypass_session_validation():
    """Bypass session validation so auth_headers work in tests."""
    with patch("app.middleware.security.session_manager.validate_session", return_value=True):
        yield


class TestSystemRouter:
    """Tests for system endpoints (/, /health, /ready, /metrics)."""

    # ==================== Root ====================

    def test_root_returns_api_info(self, client):
        """Root endpoint returns API info when no frontend build exists."""
        with patch("os.path.exists", return_value=False):
            resp = client.get("/")
            assert resp.status_code == 200
            data = resp.json()
            assert "name" in data
            assert "status" in data
            assert data["status"] == "running"

    # ==================== Health Check ====================

    def test_health_check(self, client):
        """Health check returns status."""
        with (
            patch("app.services.vectordb.get_vector_db") as mock_vdb,
            patch("app.database.async_engine") as mock_engine,
        ):
            mock_db = AsyncMock()
            mock_db.get_stats = AsyncMock(return_value={"total_chunks": 100})
            mock_vdb.return_value = mock_db

            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock(return_value=False)
            mock_engine.connect.return_value = mock_conn

            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert "status" in data
            assert "timestamp" in data
            # In debug mode, detailed components are always returned
            assert "components" in data

    def test_health_check_degraded(self, client):
        """Health check returns degraded when components fail."""
        with (
            patch("app.services.vectordb.get_vector_db", side_effect=RuntimeError("VDB down")),
            patch("app.database.async_engine") as mock_engine,
        ):
            # Router treats infrastructure errors (OperationalError/DBAPIError/OSError)
            # as a degraded component; other exceptions propagate.
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock(side_effect=OSError("DB down"))
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock(return_value=False)
            mock_engine.connect.return_value = mock_conn

            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "degraded"

    # ==================== Readiness Check ====================

    def test_ready_check(self, client):
        """Readiness check returns ready when all services up."""
        with (
            patch("app.services.vectordb.get_vector_db") as mock_vdb,
            patch("app.database.async_engine") as mock_engine,
            patch("app.config.settings") as mock_settings,
        ):
            mock_settings.openai_api_key = "test-key"
            mock_settings.anthropic_api_key = None
            mock_settings.redis_url = None
            mock_settings.debug = True

            mock_db = AsyncMock()
            mock_db.get_stats = AsyncMock(return_value={"total_chunks": 0})
            mock_vdb.return_value = mock_db

            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock(return_value=False)
            mock_engine.connect.return_value = mock_conn

            resp = client.get("/ready")
            assert resp.status_code == 200
            assert resp.json()["ready"] is True

    def test_ready_check_not_ready(self, client):
        """Readiness check returns 503 when services down."""
        with (
            patch("app.services.vectordb.get_vector_db", return_value=None),
            patch("app.database.async_engine") as mock_engine,
            patch("app.config.settings") as mock_settings,
        ):
            mock_settings.openai_api_key = None
            mock_settings.anthropic_api_key = None
            mock_settings.redis_url = None
            mock_settings.debug = True

            # Readiness check catches infrastructure errors only (OSError etc.)
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock(side_effect=OSError("DB down"))
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock(return_value=False)
            mock_engine.connect.return_value = mock_conn

            resp = client.get("/ready")
            assert resp.status_code == 503
            data = resp.json()
            assert data["ready"] is False
            assert len(data["issues"]) > 0

    # ==================== Metrics ====================

    def test_metrics_in_debug_mode(self, client):
        """Metrics endpoint is accessible in debug mode without auth."""
        with (
            patch("app.services.documents.document_service") as mock_docs,
            patch("app.services.vectordb.get_vector_db") as mock_vdb,
        ):
            mock_docs.documents = {}

            mock_db = AsyncMock()
            mock_db.get_stats = AsyncMock(return_value={"total_chunks": 50})
            mock_vdb.return_value = mock_db

            resp = client.get("/metrics")
            assert resp.status_code == 200
            data = resp.json()
            assert "timestamp" in data
            assert "application" in data
            assert "documents" in data
            assert data["application"]["environment"] == "development"

    def test_metrics_returns_document_counts(self, client):
        """Metrics includes document statistics."""
        mock_doc = MagicMock()
        mock_doc.status = MagicMock(value="indexed")
        mock_doc.chunk_count = 10

        with (
            patch("app.services.documents.document_service") as mock_docs,
            patch("app.services.vectordb.get_vector_db") as mock_vdb,
        ):
            mock_docs.documents = {"doc1": mock_doc}

            mock_db = AsyncMock()
            mock_db.get_stats = AsyncMock(return_value={"total_chunks": 10})
            mock_vdb.return_value = mock_db

            resp = client.get("/metrics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["documents"]["total_count"] == 1
            assert data["documents"]["indexed_count"] == 1
            assert data["documents"]["total_chunks"] == 10
