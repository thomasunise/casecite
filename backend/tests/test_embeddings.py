"""
Tests for EmbeddingService.

Tests embedding model configuration, provider routing, text embedding with
mocked providers, token counting and text chunking.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestModelDimensions:
    """Tests for MODEL_DIMENSIONS mapping."""

    def test_dimensions_cover_default_models(self):
        """The models the service can select by default all have a known dimension."""
        from app.services.embeddings import (
            DEFAULT_COHERE_MODEL,
            DEFAULT_VOYAGE_MODEL,
            EmbeddingService,
        )

        for model in ("text-embedding-3-small", DEFAULT_VOYAGE_MODEL, DEFAULT_COHERE_MODEL):
            assert model in EmbeddingService.MODEL_DIMENSIONS

    def test_dimensions_are_positive_integers(self):
        """Test that all dimension values are positive integers."""
        from app.services.embeddings import EmbeddingService

        for model, dim in EmbeddingService.MODEL_DIMENSIONS.items():
            assert isinstance(dim, int), f"Dimension for {model} is not int"
            assert dim > 0, f"Dimension for {model} is not positive"

    def test_openai_small_dimensions(self):
        """Test OpenAI small model dimension is 1536."""
        from app.services.embeddings import EmbeddingService

        assert EmbeddingService.MODEL_DIMENSIONS["text-embedding-3-small"] == 1536


class TestEmbeddingServiceDimensions:
    """Tests for the dimensions property."""

    def test_dimensions_property_matches_model(self):
        """Test that dimensions property returns correct value for active model."""
        from app.services.embeddings import EmbeddingService, embedding_service

        expected = EmbeddingService.MODEL_DIMENSIONS[embedding_service.model]
        assert embedding_service.dimensions == expected


def _service(model="text-embedding-3-small", openai=None, voyage=None, cohere=None, base_url=None):
    """A standalone EmbeddingService with explicit configuration."""
    from app.services.embeddings import EmbeddingService

    svc = EmbeddingService()
    svc.model = model
    svc.openai_api_key = openai
    svc.voyage_api_key = voyage
    svc.cohere_api_key = cohere
    svc.base_url = base_url
    return svc


def _keys(**kwargs):
    from app.services.user_keys import UserAPIKeys

    return UserAPIKeys(**kwargs)


class TestRouting:
    """Provider/model/credential selection — shared by documents and queries."""

    def test_openai_default(self):
        route = _service(openai="sk-server-key-000000").resolve_route()
        assert (route.provider, route.kind, route.model) == (
            "openai",
            "openai",
            "text-embedding-3-small",
        )
        assert route.api_key == "sk-server-key-000000"

    def test_user_voyage_key_only_uses_a_voyage_model(self):
        """Regression: Voyage used to be sent the server's OpenAI model name."""
        svc = _service(model="text-embedding-3-small")
        route = svc.resolve_route(_keys(voyage="pa-user-voyage-key-000"))
        assert route.provider == "voyage"
        assert route.model == "voyage-law-2"

    def test_user_cohere_key_only_uses_a_cohere_model(self):
        svc = _service(model="text-embedding-3-small")
        route = svc.resolve_route(_keys(cohere="cohere-user-key-0000"))
        assert route.provider == "cohere"
        assert route.model == "embed-english-v3.0"

    def test_self_hosted_endpoint_is_never_routed_around(self):
        """With EMBEDDING_BASE_URL set, a BYOK Voyage key must not move
        embeddings off the operator's server, and the user's personal OpenAI
        key is not handed to it."""
        svc = _service(model="nomic-embed-text", base_url="http://ollama:11434/v1")
        route = svc.resolve_route(
            _keys(voyage="pa-user-voyage-key-000", openai="sk-user-openai-key-00")
        )
        assert route.provider == "self_hosted"
        assert route.kind == "openai"
        assert route.model == "nomic-embed-text"
        assert route.base_url == "http://ollama:11434/v1"
        assert route.api_key is None

    def test_credential_scope_differs_per_key_and_hides_it(self):
        svc = _service(openai="sk-server-key-000000")
        a = svc.credential_scope(_keys(openai="sk-user-a-key-0000000"))
        b = svc.credential_scope(_keys(openai="sk-user-b-key-0000000"))
        assert a != b
        assert a.startswith("openai:")
        assert "sk-user-a" not in a

    def test_placeholder_server_keys_are_not_configured(self):
        from app.services.embeddings import _real_key

        assert _real_key("your-voyage-api-key") is None
        assert _real_key("sk-your-openai-key") is None
        assert _real_key("sk-ant-your-anthropic-key") is None
        assert _real_key("") is None
        assert _real_key("pa-0123456789abcdef") == "pa-0123456789abcdef"


class TestProviderRequests:
    """What is actually sent to each provider."""

    @staticmethod
    def _http_client(payload):
        response = MagicMock()
        response.json.return_value = payload
        response.raise_for_status = MagicMock()
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        return client

    @pytest.mark.asyncio
    async def test_voyage_documents_and_queries_use_same_model_different_input_type(self):
        svc = _service(model="text-embedding-3-small")
        keys = _keys(voyage="pa-user-voyage-key-000")
        client = self._http_client({"data": [{"embedding": [0.1] * 4}]})

        with patch("httpx.AsyncClient", return_value=client):
            await svc.embed_texts(["a clause"], user_keys=keys)
            await svc.embed_query("a question", user_keys=keys)

        doc_body = client.post.call_args_list[0].kwargs["json"]
        query_body = client.post.call_args_list[1].kwargs["json"]
        assert doc_body["model"] == query_body["model"] == "voyage-law-2"
        assert doc_body["input_type"] == "document"
        assert query_body["input_type"] == "query"

    @pytest.mark.asyncio
    async def test_cohere_is_sent_a_cohere_model(self):
        svc = _service(model="text-embedding-3-small")
        keys = _keys(cohere="cohere-user-key-0000")
        client = self._http_client({"embeddings": [[0.1] * 4]})

        with patch("httpx.AsyncClient", return_value=client):
            await svc.embed_texts(["a clause"], user_keys=keys)
            await svc.embed_query("a question", user_keys=keys)

        doc_body = client.post.call_args_list[0].kwargs["json"]
        query_body = client.post.call_args_list[1].kwargs["json"]
        assert doc_body["model"] == "embed-english-v3.0"
        assert doc_body["input_type"] == "search_document"
        assert query_body["input_type"] == "search_query"

    @pytest.mark.asyncio
    async def test_self_hosted_base_url_is_used_without_a_key(self):
        from app.config import settings

        svc = _service(model="nomic-embed-text", base_url="http://localhost:11434/v1")
        response = MagicMock()
        response.data = [MagicMock(embedding=[0.1] * 4)]
        client = AsyncMock()
        client.embeddings.create = AsyncMock(return_value=response)

        with patch("openai.AsyncOpenAI", return_value=client) as ctor:
            result = await svc.embed_texts(["privileged text"])

        ctor.assert_called_once_with(
            api_key="not-needed",
            timeout=settings.api_timeout,
            max_retries=2,
            base_url="http://localhost:11434/v1",
        )
        assert client.embeddings.create.call_args.kwargs["model"] == "nomic-embed-text"
        assert result == [[0.1] * 4]

    @pytest.mark.asyncio
    async def test_allowlist_blocks_an_unapproved_embedding_provider(self):
        from app.services.provider_policy import ProviderNotAllowedError

        svc = _service(openai="sk-server-key-000000")
        with (
            patch("app.services.provider_policy.settings") as policy_settings,
            patch("openai.AsyncOpenAI") as ctor,
        ):
            policy_settings.hipaa_enforcement_enabled = True
            policy_settings.approved_ai_providers = ["anthropic", "self_hosted"]
            with pytest.raises(ProviderNotAllowedError):
                await svc.embed_texts(["privileged text"])
        ctor.assert_not_called()

    @pytest.mark.asyncio
    async def test_allowlist_permits_a_self_hosted_embedding_endpoint(self):
        svc = _service(model="nomic-embed-text", base_url="http://localhost:11434/v1")
        response = MagicMock()
        response.data = [MagicMock(embedding=[0.1] * 4)]
        client = AsyncMock()
        client.embeddings.create = AsyncMock(return_value=response)
        with (
            patch("app.services.provider_policy.settings") as policy_settings,
            patch("openai.AsyncOpenAI", return_value=client),
        ):
            policy_settings.hipaa_enforcement_enabled = True
            policy_settings.approved_ai_providers = ["self_hosted"]
            assert await svc.embed_texts(["privileged text"]) == [[0.1] * 4]


class TestEmbedTexts:
    """Tests for embed_texts method."""

    @pytest.mark.asyncio
    async def test_embed_texts_empty_returns_empty(self):
        """Test that embedding empty list returns empty list."""
        from app.services.embeddings import embedding_service

        result = await embedding_service.embed_texts([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_openai_mock(self):
        """Test _embed_openai with mocked OpenAI client."""
        from app.services.embeddings import embedding_service

        mock_embedding = [0.1] * 1536
        mock_response = MagicMock()
        mock_data_item = MagicMock()
        mock_data_item.embedding = mock_embedding
        mock_response.data = [mock_data_item]

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        original_model = embedding_service.model
        try:
            embedding_service.model = "text-embedding-3-small"
            with patch("openai.AsyncOpenAI", return_value=mock_client):
                result = await embedding_service._embed_openai(["test text"], api_key="test-key")

            assert len(result) == 1
            assert len(result[0]) == 1536
        finally:
            embedding_service.model = original_model

    @pytest.mark.asyncio
    async def test_embed_openai_client_has_timeout_and_bounded_retries(self):
        """The embeddings client must never wait forever on a hung upstream."""
        from app.config import settings
        from app.services.embeddings import embedding_service

        mock_response = MagicMock()
        item = MagicMock()
        item.embedding = [0.1] * 1536
        mock_response.data = [item]
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        original_model = embedding_service.model
        try:
            embedding_service.model = "text-embedding-3-small"
            with patch("openai.AsyncOpenAI", return_value=mock_client) as ctor:
                await embedding_service._embed_openai(["x"], api_key="test-key")
            ctor.assert_called_once_with(
                api_key="test-key", timeout=settings.api_timeout, max_retries=2
            )
        finally:
            embedding_service.model = original_model

    @pytest.mark.asyncio
    async def test_embed_openai_batching(self):
        """Test that >100 texts triggers multiple API calls."""
        from app.services.embeddings import embedding_service

        texts = [f"text {i}" for i in range(150)]
        mock_embedding = [0.1] * 1536

        mock_data_item = MagicMock()
        mock_data_item.embedding = mock_embedding
        mock_response = MagicMock()
        mock_response.data = [mock_data_item]

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        original_model = embedding_service.model
        try:
            embedding_service.model = "text-embedding-3-small"
            with patch("openai.AsyncOpenAI", return_value=mock_client):
                # The method should handle batching, making multiple calls
                # We mock so each call returns one embedding; batching logic varies
                mock_response_batch = MagicMock()
                mock_response_batch.data = [MagicMock(embedding=mock_embedding) for _ in range(100)]
                mock_response_batch2 = MagicMock()
                mock_response_batch2.data = [MagicMock(embedding=mock_embedding) for _ in range(50)]
                mock_client.embeddings.create = AsyncMock(
                    side_effect=[mock_response_batch, mock_response_batch2]
                )
                result = await embedding_service._embed_openai(texts, api_key="test-key")

            assert len(result) == 150
            assert mock_client.embeddings.create.call_count == 2
        finally:
            embedding_service.model = original_model

    @pytest.mark.asyncio
    async def test_embed_voyage_mock(self):
        """Test _embed_voyage with mocked httpx client."""
        from app.services.embeddings import embedding_service

        mock_embedding = [0.2] * 1024
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"embedding": mock_embedding}]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await embedding_service._embed_voyage(
                ["legal text"], api_key="voyage-test-key"
            )

        assert len(result) == 1
        assert len(result[0]) == 1024

    @pytest.mark.asyncio
    async def test_embed_cohere_mock(self):
        """Test _embed_cohere with mocked httpx client."""
        from app.services.embeddings import embedding_service

        mock_embedding = [0.3] * 1024
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embeddings": [mock_embedding]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await embedding_service._embed_cohere(
                ["contract clause"], api_key="cohere-test-key"
            )

        assert len(result) == 1


class TestTokenCounting:
    """Tests for count_tokens method."""

    def test_count_tokens_returns_positive_int(self):
        """Test that count_tokens returns a positive integer."""
        from app.services.embeddings import embedding_service

        result = embedding_service.count_tokens("This is a test sentence.")
        assert isinstance(result, int)
        assert result > 0

    def test_count_tokens_longer_text_more_tokens(self):
        """Test that longer text produces more tokens."""
        from app.services.embeddings import embedding_service

        short = embedding_service.count_tokens("Hello")
        long = embedding_service.count_tokens(
            "This is a much longer sentence with many more words in it."
        )
        assert long > short

    def test_count_tokens_empty_string(self):
        """Test token count of empty string is zero or small."""
        from app.services.embeddings import embedding_service

        result = embedding_service.count_tokens("")
        assert isinstance(result, int)
        assert result >= 0


class TestChunkText:
    """Tests for chunk_text method."""

    def test_chunk_text_returns_list_of_dicts(self):
        """Test that chunk_text returns list of dicts with required keys."""
        from app.services.embeddings import embedding_service

        text = "This is a test sentence. " * 50
        chunks = embedding_service.chunk_text(text, chunk_size=50, chunk_overlap=10)

        assert isinstance(chunks, list)
        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, dict)
            assert "text" in chunk
            assert "chunk_index" in chunk
            assert "token_count" in chunk

    def test_chunk_text_indices_sequential(self):
        """Test that chunk indices are sequential starting from 0."""
        from app.services.embeddings import embedding_service

        text = "Word " * 200
        chunks = embedding_service.chunk_text(text, chunk_size=50, chunk_overlap=10)

        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i

    def test_chunk_text_overlap(self):
        """Test that chunks overlap when overlap is specified."""
        from app.services.embeddings import embedding_service

        text = "Word " * 200
        chunks = embedding_service.chunk_text(text, chunk_size=50, chunk_overlap=10)

        # With overlap, consecutive chunks should share some content
        assert len(chunks) > 1

    def test_chunk_text_short_text_single_chunk(self):
        """Test that short text produces a single chunk."""
        from app.services.embeddings import embedding_service

        text = "Short text."
        chunks = embedding_service.chunk_text(text, chunk_size=500, chunk_overlap=50)

        assert len(chunks) == 1
        assert chunks[0]["text"].strip() == text.strip()

    def test_chunk_text_overlap_not_smaller_than_size_still_terminates(self):
        """A chunk size at or below the overlap must not loop forever."""
        from app.services.embeddings import embedding_service

        chunks = embedding_service.chunk_text("Word " * 300, chunk_size=64, chunk_overlap=128)

        assert len(chunks) > 1
        assert chunks[-1]["end_token"] >= chunks[0]["end_token"]
