# ADR-002: Vector Database Strategy

**Status:** Accepted
**Date:** 2025-01-15
**Decision makers:** Core maintainers

## Context

CaseCite's RAG pipeline requires a vector database to store and search document embeddings. The platform needs to support both zero-infrastructure local development and horizontally scalable production deployments. We also need to support multiple embedding providers (OpenAI, Voyage AI, Cohere) with different dimensionalities (1024–3072).

The main options considered:

1. **ChromaDB only** — Embedded, local, SQLite-backed
2. **Pinecone only** — Cloud-hosted, managed, scalable
3. **ChromaDB default + Pinecone option** — Abstraction layer with runtime backend selection
4. **pgvector** — PostgreSQL extension, co-located with application database
5. **Weaviate / Qdrant / Milvus** — Self-hosted vector databases with clustering support

## Decision

We chose **ChromaDB as the default with Pinecone as an optional backend** (option 3), switchable via a single environment variable (`VECTOR_DB=chroma|pinecone`).

The abstraction is implemented as a Strategy pattern:

- `VectorDBBase` (abstract base class) defines the common interface: `add_documents()`, `search()`, `delete()`, `delete_by_document()`, `get_stats()`
- `ChromaDB(VectorDBBase)` — Embedded client, persists to `./data/chroma`, zero external dependencies
- `PineconeDB(VectorDBBase)` — Cloud client, auto-creates index on first connection
- `get_vector_db()` — Singleton factory that reads `VECTOR_DB` from config and returns the appropriate implementation

All search operations require a `user_id` filter for tenant isolation. The search function raises `ValueError` if the filter is missing.

The app starts successfully even if the vector DB fails to initialize (`get_vector_db()` returns `None`), allowing non-RAG features to work.

### Embedding providers

The platform supports four embedding providers with automatic fallback:

| Provider | Model | Dimensions | Notes |
|----------|-------|------------|-------|
| OpenAI | text-embedding-3-small | 1536 | Default (most users have keys) |
| Voyage AI | voyage-law-2 | 1024 | Legal-specific, recommended for accuracy |
| Cohere | embed-english-v3.0 | 1024 | Alternative provider |
| Cohere | embed-multilingual-v3.0 | 1024 | Multi-language support |

Provider selection follows BYOK: if a user provides a Voyage AI key in Settings, their documents use legal-optimized embeddings. Otherwise, the server-default OpenAI model is used.

## Consequences

### Positive

- **Zero-setup development.** `docker compose up` gives you a working RAG pipeline with no external accounts, API keys, or cloud services. ChromaDB persists to a local directory.
- **One-line production upgrade.** Switching to Pinecone requires only `VECTOR_DB=pinecone` plus API credentials. No code changes, no migration scripts for the application layer.
- **Cost flexibility.** Small firms and solo attorneys use ChromaDB (free). Larger deployments with thousands of documents scale to Pinecone (pay-per-query).
- **Graceful degradation.** If vector DB initialization fails, the application starts normally. Users can still use document drafting, discovery, and other non-RAG features.
- **Legal-optimized embeddings.** Voyage AI's `voyage-law-2` model is purpose-trained on legal corpora, improving retrieval accuracy for case law and statutes.

### Negative

- **ChromaDB limits horizontal scaling.** ChromaDB uses SQLite internally, which does not support concurrent writes from multiple processes. This forces the production deployment to run a single uvicorn worker, capping throughput at ~200-400 req/s.
- **Dimension mismatch risk.** If a user changes embedding providers (e.g., OpenAI 1536-dim to Voyage 1024-dim), existing vectors become incompatible. The platform includes diagnostic endpoints to detect this, but recovery requires clearing and re-indexing all documents.
- **Two backends to maintain.** Bug fixes, new features, and filter syntax must be implemented in both `ChromaDB` and `PineconeDB` classes. Metadata handling differs (Pinecone truncates to 1000 bytes).
- **No hybrid search in Pinecone.** ChromaDB supports distance-based search only. The BM25 keyword component of hybrid search runs separately against PostgreSQL, not the vector DB. This coupling isn't captured in the abstraction.

### Scaling path

To unlock horizontal scaling:
1. Set `VECTOR_DB=pinecone` and provide API credentials
2. Increase `UVICORN_WORKERS` in `start.sh` (no longer constrained by SQLite locking)
3. Deploy multiple backend instances behind a load balancer
4. PostgreSQL and Redis already support multi-instance deployments

### Alternatives rejected

- **pgvector**: Would couple vector search to the relational database, complicating scaling (can't scale search independently of transactions). Also lacks the embedding-native features of purpose-built vector DBs.
- **Weaviate/Qdrant/Milvus**: Require dedicated infrastructure (JVM/Rust runtimes, clustering coordination). Adds operational burden disproportionate to current scale. Pinecone provides managed scaling without self-hosting.
- **Pinecone only**: Would require every developer and small deployment to have a Pinecone account and API key. Eliminates the zero-setup local development experience.
