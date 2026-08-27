"""
Integration tests for the Chat router (/chat).
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import AsyncMock, patch


class TestChatRouter:
    """Tests for /chat endpoints."""

    def test_chat_post_with_auth(self, app, client, auth_headers):
        """POST /chat with auth and mocked RAG service returns 200."""
        mock_result = {
            "content": "This is a test legal response.",
            "citations": [],
            "stats": {
                "docs_searched": 10,
                "chunks_retrieved": 2,
                "processing_time": "0.5s",
                "model": "gpt-4o",
            },
        }

        with patch(
            "app.routers.chat.rag_service.generate_response",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client.post(
                "/api/v1/chat",
                json={
                    "query": "What is the statute of limitations for breach of contract?",
                    "mode": "research",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert "content" in data
            assert "id" in data
            assert "citations" in data

    def test_chat_post_no_auth(self, client):
        """POST /chat without auth returns 401 or 403."""
        response = client.post(
            "/api/v1/chat",
            json={"query": "test question", "mode": "research"},
        )
        assert response.status_code in [401, 403]
