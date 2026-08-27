"""
Embedding Service - Legal-Optimized Text Embeddings

Supports:
- OpenAI embeddings (text-embedding-3-small/large)
- Voyage AI legal embeddings (voyage-law-2) - RECOMMENDED for legal
- Cohere embeddings
- Local sentence-transformers

voyage-law-2 is specifically trained on legal text and outperforms
general-purpose models on legal retrieval tasks.
"""

from enum import Enum
from typing import TYPE_CHECKING, Optional

import httpx
import tiktoken

from app.config import settings

if TYPE_CHECKING:
    from app.services.user_keys import UserAPIKeys


class EmbeddingModel(str, Enum):
    # OpenAI (text-embedding-3-* remain OpenAI's current embedding models)
    OPENAI_SMALL = "text-embedding-3-small"  # 1536 dimensions
    OPENAI_LARGE = "text-embedding-3-large"  # 3072 dimensions
    OPENAI_ADA = "text-embedding-ada-002"  # Legacy, 1536 dimensions

    # Voyage AI - voyage-law-2 stays the recommended legal-optimized model;
    # voyage-4 / voyage-3.5 are the current general-purpose models.
    VOYAGE_LAW_2 = "voyage-law-2"  # 1024 dimensions, legal-optimized (recommended for legal)
    VOYAGE_4 = "voyage-4"  # current general-purpose
    VOYAGE_4_LITE = "voyage-4-lite"  # current, cost-efficient
    VOYAGE_3_5 = "voyage-3.5"  # general
    VOYAGE_LARGE = "voyage-large-2"  # legacy general

    # Cohere - embed-v4.0 is the current multimodal model (1536 dim)
    COHERE_V4 = "embed-v4.0"  # 1536 dimensions, multimodal (current)
    COHERE_ENGLISH = "embed-english-v3.0"  # 1024 dimensions (legacy)
    COHERE_MULTILINGUAL = "embed-multilingual-v3.0"


class EmbeddingService:
    """
    Multi-provider embedding service with legal optimization.

    For legal applications, voyage-law-2 is strongly recommended
    as it's trained specifically on legal text.
    """

    # Model dimensions
    MODEL_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
        "voyage-law-2": 1024,
        "voyage-4": 1024,
        "voyage-4-lite": 1024,
        "voyage-3.5": 1024,
        "voyage-large-2": 1536,
        "embed-v4.0": 1536,
        "embed-english-v3.0": 1024,
        "embed-multilingual-v3.0": 1024,
    }

    def __init__(self):
        self.openai_api_key = settings.openai_api_key
        self.voyage_api_key = getattr(settings, "voyage_api_key", None)
        self.cohere_api_key = getattr(settings, "cohere_api_key", None)

        # Select model based on available API keys
        preferred_model = getattr(settings, "embedding_model", settings.openai_embedding_model)
        if (
            preferred_model.startswith("voyage")
            and not self.voyage_api_key
            or preferred_model.startswith("embed-")
            and not self.cohere_api_key
        ):
            self.model = settings.openai_embedding_model  # Fallback to OpenAI
        else:
            self.model = preferred_model

        # Initialize tokenizer for chunking
        try:
            self.tokenizer = tiktoken.encoding_for_model("gpt-4")
        except (KeyError, ValueError):
            self.tokenizer = tiktoken.get_encoding("cl100k_base")

    @property
    def dimensions(self) -> int:
        """Get embedding dimensions for current model."""
        return self.MODEL_DIMENSIONS.get(self.model, 1536)

    def set_model(self, model: str):
        """Change the embedding model."""
        self.model = model

    async def embed_text(self, text: str, user_keys: Optional["UserAPIKeys"] = None) -> list[float]:
        """Generate embedding for a single text."""
        embeddings = await self.embed_texts([text], user_keys=user_keys)
        return embeddings[0]

    async def embed_texts(
        self, texts: list[str], user_keys: Optional["UserAPIKeys"] = None
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.
            user_keys: Optional user-provided API keys for BYOK.
        """
        if not texts:
            return []

        # Get API keys - prefer user keys (BYOK), fall back to server keys
        openai_key = user_keys.openai if user_keys and user_keys.openai else self.openai_api_key
        voyage_key = user_keys.voyage if user_keys and user_keys.voyage else self.voyage_api_key
        cohere_key = user_keys.cohere if user_keys and user_keys.cohere else self.cohere_api_key

        # Route to appropriate provider
        # If user provides a BYOK key for a provider that matches the configured model, use it.
        # If user provides a key for a different provider than the server default,
        # prefer the provider that has an available key (user > server).
        model = self.model

        # If server model is OpenAI but user only provided Voyage key, use Voyage
        if not model.startswith("voyage") and voyage_key and not openai_key:
            model = "voyage-law-2"
        elif not model.startswith("embed-") and cohere_key and not openai_key and not voyage_key:
            model = "embed-english-v3.0"

        if model.startswith("voyage"):
            return await self._embed_voyage(texts, api_key=voyage_key)
        elif model.startswith("embed-"):  # Cohere
            return await self._embed_cohere(texts, api_key=cohere_key)
        else:  # OpenAI
            return await self._embed_openai(texts, api_key=openai_key)

    async def _embed_openai(
        self, texts: list[str], api_key: str | None = None
    ) -> list[list[float]]:
        """Generate embeddings using OpenAI API."""
        from openai import AsyncOpenAI

        key = api_key or self.openai_api_key
        if not key:
            raise ValueError(
                "OpenAI API key not configured. Please provide your API key in Settings."
            )

        # Embeddings always go to api.openai.com (not the chat base_url), so
        # this is built directly rather than via llm_clients.make_openai — but
        # with the same timeout/retry bounds so a hung request cannot pin an
        # indexing job forever.
        client = AsyncOpenAI(api_key=key, timeout=settings.api_timeout, max_retries=2)
        batch_size = 100
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = await client.embeddings.create(model=self.model, input=batch)
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def _embed_voyage(
        self, texts: list[str], api_key: str | None = None
    ) -> list[list[float]]:
        """
        Generate embeddings using Voyage AI.

        voyage-law-2 is specifically optimized for legal text:
        - Trained on legal documents, case law, statutes
        - Better understanding of legal terminology
        - Improved retrieval for legal queries

        API: https://docs.voyageai.com/
        """
        key = api_key or self.voyage_api_key
        if not key:
            raise ValueError(
                "Voyage API key not configured. Please provide your Voyage API key in Settings."
            )

        all_embeddings = []
        batch_size = 128  # Voyage allows larger batches

        async with httpx.AsyncClient(timeout=60.0) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]

                response = await client.post(
                    "https://api.voyageai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "input": batch,
                        "input_type": "document",  # or "query" for search queries
                    },
                )
                response.raise_for_status()
                data = response.json()

                # Extract embeddings in order
                batch_embeddings = [item["embedding"] for item in data["data"]]
                all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def embed_query(
        self, query: str, user_keys: Optional["UserAPIKeys"] = None
    ) -> list[float]:
        """
        Generate embedding for a search query.

        Voyage AI distinguishes between document and query embeddings
        for better retrieval performance.
        """
        voyage_key = user_keys.voyage if user_keys and user_keys.voyage else self.voyage_api_key

        if self.model.startswith("voyage"):
            return await self._embed_voyage_query(query, api_key=voyage_key)
        else:
            return await self.embed_text(query, user_keys=user_keys)

    async def _embed_voyage_query(self, query: str, api_key: str | None = None) -> list[float]:
        """Generate query embedding using Voyage AI."""
        key = api_key or self.voyage_api_key
        if not key:
            raise ValueError(
                "Voyage API key not configured. Please provide your Voyage API key in Settings."
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": [query],
                    "input_type": "query",  # Optimize for query
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]

    async def _embed_cohere(
        self, texts: list[str], api_key: str | None = None
    ) -> list[list[float]]:
        """Generate embeddings using Cohere API."""
        key = api_key or self.cohere_api_key
        if not key:
            raise ValueError(
                "Cohere API key not configured. Please provide your Cohere API key in Settings."
            )

        all_embeddings = []
        batch_size = 96  # Cohere limit

        async with httpx.AsyncClient(timeout=60.0) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]

                response = await client.post(
                    "https://api.cohere.ai/v1/embed",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "texts": batch,
                        "input_type": "search_document",
                        "truncate": "END",
                    },
                )
                response.raise_for_status()
                data = response.json()
                all_embeddings.extend(data["embeddings"])

        return all_embeddings

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.tokenizer.encode(text))

    def chunk_text(
        self, text: str, chunk_size: int = None, chunk_overlap: int = None
    ) -> list[dict]:
        """Split text into overlapping chunks."""
        chunk_size = chunk_size or getattr(settings, "chunk_size", 512)
        chunk_overlap = chunk_overlap or getattr(settings, "chunk_overlap", 128)

        tokens = self.tokenizer.encode(text)
        chunks = []
        start = 0
        chunk_index = 0

        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = self.tokenizer.decode(chunk_tokens)

            chunks.append(
                {
                    "text": chunk_text,
                    "chunk_index": chunk_index,
                    "token_count": len(chunk_tokens),
                    "start_token": start,
                    "end_token": end,
                }
            )

            start += chunk_size - chunk_overlap
            chunk_index += 1

        return chunks

    def chunk_legal_document(
        self, text: str, chunk_size: int = None, preserve_sections: bool = True
    ) -> list[dict]:
        """
        Chunk a legal document while preserving structure.

        Legal documents have specific structures (sections, paragraphs,
        numbered items) that should be preserved when possible.
        """
        chunk_size = chunk_size or getattr(settings, "chunk_size", 512)

        if not preserve_sections:
            return self.chunk_text(text, chunk_size)

        import re

        # Split by common legal document sections
        section_patterns = [
            r"\n(?=SECTION\s+\d+)",
            r"\n(?=Article\s+[IVX\d]+)",
            r"\n(?=§\s*\d+)",
            r"\n(?=\d+\.\s+[A-Z])",  # Numbered paragraphs
            r"\n(?=[A-Z]\.\s+)",  # Lettered paragraphs
            r"\n{2,}",  # Double newlines
        ]

        # Combine patterns
        combined_pattern = "|".join(section_patterns)
        sections = re.split(combined_pattern, text)

        chunks = []
        current_chunk = ""
        current_tokens = 0
        chunk_index = 0

        for section in sections:
            section = section.strip()
            if not section:
                continue

            section_tokens = self.count_tokens(section)

            # If section alone is too big, use regular chunking
            if section_tokens > chunk_size:
                # First, save current chunk if exists
                if current_chunk:
                    chunks.append(
                        {
                            "text": current_chunk.strip(),
                            "chunk_index": chunk_index,
                            "token_count": current_tokens,
                            "section_boundary": True,
                        }
                    )
                    chunk_index += 1
                    current_chunk = ""
                    current_tokens = 0

                # Chunk the large section
                sub_chunks = self.chunk_text(section, chunk_size)
                for sub in sub_chunks:
                    sub["chunk_index"] = chunk_index
                    chunks.append(sub)
                    chunk_index += 1
            else:
                # Check if adding section exceeds limit
                if current_tokens + section_tokens > chunk_size:
                    # Save current chunk
                    if current_chunk:
                        chunks.append(
                            {
                                "text": current_chunk.strip(),
                                "chunk_index": chunk_index,
                                "token_count": current_tokens,
                                "section_boundary": True,
                            }
                        )
                        chunk_index += 1
                    current_chunk = section
                    current_tokens = section_tokens
                else:
                    # Add to current chunk
                    current_chunk += "\n\n" + section if current_chunk else section
                    current_tokens += section_tokens

        # Don't forget last chunk
        if current_chunk:
            chunks.append(
                {
                    "text": current_chunk.strip(),
                    "chunk_index": chunk_index,
                    "token_count": current_tokens,
                    "section_boundary": True,
                }
            )

        return chunks


# Singleton instance
embedding_service = EmbeddingService()
