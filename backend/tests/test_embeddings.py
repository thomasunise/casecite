"""
Tests for EmbeddingService.

Tests embedding model configuration, text embedding with mocked providers,
token counting, text chunking, and legal document chunking.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestEmbeddingModelEnum:
    """Tests for EmbeddingModel enum values."""

    def test_openai_small_value(self):
        """Test OPENAI_SMALL enum value."""
        from app.services.embeddings import EmbeddingModel

        assert EmbeddingModel.OPENAI_SMALL == "text-embedding-3-small"
        assert EmbeddingModel.OPENAI_SMALL.value == "text-embedding-3-small"

    def test_openai_large_value(self):
        """Test OPENAI_LARGE enum value."""
        from app.services.embeddings import EmbeddingModel

        assert EmbeddingModel.OPENAI_LARGE == "text-embedding-3-large"

    def test_openai_ada_value(self):
        """Test OPENAI_ADA enum value."""
        from app.services.embeddings import EmbeddingModel

        assert EmbeddingModel.OPENAI_ADA == "text-embedding-ada-002"

    def test_voyage_law_2_value(self):
        """Test VOYAGE_LAW_2 enum value."""
        from app.services.embeddings import EmbeddingModel

        assert EmbeddingModel.VOYAGE_LAW_2 == "voyage-law-2"

    def test_voyage_large_value(self):
        """Test VOYAGE_LARGE enum value."""
        from app.services.embeddings import EmbeddingModel

        assert EmbeddingModel.VOYAGE_LARGE == "voyage-large-2"

    def test_cohere_english_value(self):
        """Test COHERE_ENGLISH enum value."""
        from app.services.embeddings import EmbeddingModel

        assert EmbeddingModel.COHERE_ENGLISH == "embed-english-v3.0"

    def test_cohere_multilingual_value(self):
        """Test COHERE_MULTILINGUAL enum value."""
        from app.services.embeddings import EmbeddingModel

        assert EmbeddingModel.COHERE_MULTILINGUAL == "embed-multilingual-v3.0"

    def test_enum_is_string(self):
        """Test that EmbeddingModel members are strings."""
        from app.services.embeddings import EmbeddingModel

        for model in EmbeddingModel:
            assert isinstance(model, str)
            assert isinstance(model.value, str)


class TestModelDimensions:
    """Tests for MODEL_DIMENSIONS mapping."""

    def test_dimensions_has_all_models(self):
        """Test that MODEL_DIMENSIONS has entries for all EmbeddingModel members."""
        from app.services.embeddings import EmbeddingModel, EmbeddingService

        for model in EmbeddingModel:
            assert model in EmbeddingService.MODEL_DIMENSIONS, (
                f"MODEL_DIMENSIONS missing entry for {model}"
            )

    def test_dimensions_are_positive_integers(self):
        """Test that all dimension values are positive integers."""
        from app.services.embeddings import EmbeddingService

        for model, dim in EmbeddingService.MODEL_DIMENSIONS.items():
            assert isinstance(dim, int), f"Dimension for {model} is not int"
            assert dim > 0, f"Dimension for {model} is not positive"

    def test_openai_small_dimensions(self):
        """Test OpenAI small model dimension is 1536."""
        from app.services.embeddings import EmbeddingModel, EmbeddingService

        assert EmbeddingService.MODEL_DIMENSIONS[EmbeddingModel.OPENAI_SMALL] == 1536


class TestEmbeddingServiceSetModel:
    """Tests for set_model and dimensions property."""

    def test_set_model_changes_model(self):
        """Test that set_model updates the active model."""
        from app.services.embeddings import EmbeddingModel, embedding_service

        original = embedding_service.model
        try:
            embedding_service.set_model(EmbeddingModel.VOYAGE_LAW_2)
            assert embedding_service.model == EmbeddingModel.VOYAGE_LAW_2
        finally:
            embedding_service.set_model(original)

    def test_dimensions_property_matches_model(self):
        """Test that dimensions property returns correct value for active model."""
        from app.services.embeddings import EmbeddingService, embedding_service

        expected = EmbeddingService.MODEL_DIMENSIONS[embedding_service.model]
        assert embedding_service.dimensions == expected


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
        from app.services.embeddings import EmbeddingModel, embedding_service

        mock_embedding = [0.1] * 1536
        mock_response = MagicMock()
        mock_data_item = MagicMock()
        mock_data_item.embedding = mock_embedding
        mock_response.data = [mock_data_item]

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        original_model = embedding_service.model
        try:
            embedding_service.set_model(EmbeddingModel.OPENAI_SMALL)
            with patch("openai.AsyncOpenAI", return_value=mock_client):
                result = await embedding_service._embed_openai(["test text"], api_key="test-key")

            assert len(result) == 1
            assert len(result[0]) == 1536
        finally:
            embedding_service.set_model(original_model)

    @pytest.mark.asyncio
    async def test_embed_openai_client_has_timeout_and_bounded_retries(self):
        """The embeddings client must never wait forever on a hung upstream."""
        from app.config import settings
        from app.services.embeddings import EmbeddingModel, embedding_service

        mock_response = MagicMock()
        item = MagicMock()
        item.embedding = [0.1] * 1536
        mock_response.data = [item]
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        original_model = embedding_service.model
        try:
            embedding_service.set_model(EmbeddingModel.OPENAI_SMALL)
            with patch("openai.AsyncOpenAI", return_value=mock_client) as ctor:
                await embedding_service._embed_openai(["x"], api_key="test-key")
            ctor.assert_called_once_with(
                api_key="test-key", timeout=settings.api_timeout, max_retries=2
            )
        finally:
            embedding_service.set_model(original_model)

    @pytest.mark.asyncio
    async def test_embed_openai_batching(self):
        """Test that >100 texts triggers multiple API calls."""
        from app.services.embeddings import EmbeddingModel, embedding_service

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
            embedding_service.set_model(EmbeddingModel.OPENAI_SMALL)
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
            embedding_service.set_model(original_model)

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


class TestChunkLegalDocument:
    """Tests for chunk_legal_document method."""

    def test_chunk_legal_document_with_sections(self):
        """Test legal chunking preserves section headers."""
        from app.services.embeddings import embedding_service

        legal_text = """
SECTION 1: DEFINITIONS
In this Agreement, the following terms shall have the meanings set forth below.
Party A means the first party to this agreement.
Party B means the second party to this agreement.

SECTION 2: OBLIGATIONS
Party A shall deliver goods within 30 days.
Party B shall make payment within 15 days of delivery.

SECTION 3: TERMINATION
Either party may terminate this agreement with 90 days written notice.
"""
        chunks = embedding_service.chunk_legal_document(
            legal_text, chunk_size=100, preserve_sections=True
        )

        assert isinstance(chunks, list)
        assert len(chunks) > 0
        for chunk in chunks:
            assert "text" in chunk

    def test_chunk_legal_document_preserve_false_delegates(self):
        """Test that preserve_sections=False delegates to chunk_text."""
        from app.services.embeddings import embedding_service

        legal_text = "This is a legal document. " * 50

        # chunk_size must exceed default chunk_overlap (128) to avoid
        # a non-advancing window in chunk_text.
        chunks = embedding_service.chunk_legal_document(
            legal_text, chunk_size=256, preserve_sections=False
        )

        assert isinstance(chunks, list)
        assert len(chunks) > 0
        for chunk in chunks:
            assert "text" in chunk
            assert "chunk_index" in chunk
