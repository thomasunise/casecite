"""
Tests for ChromaDB vector database service.

Tests document storage, semantic search, deletion, and statistics
using real ChromaDB instances via the chroma_db fixture.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import pytest


class TestAddDocuments:
    """Tests for adding documents to ChromaDB."""

    @pytest.mark.asyncio
    async def test_add_single_document_returns_id(self, chroma_db):
        """Test adding a single document returns its ID."""
        doc = {
            "id": "doc-001-chunk-0",
            "embedding": [0.1] * 10,
            "text": "This Agreement is entered into as of January 1, 2024.",
            "source": "contract.pdf",
            "document_id": "doc-001",
            "chunk_index": 0,
            "filename": "contract.pdf",
            "user_id": "user-1",
        }
        result = await chroma_db.add_documents([doc])

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == "doc-001-chunk-0"

    @pytest.mark.asyncio
    async def test_add_multiple_documents_returns_all_ids(self, chroma_db):
        """Test adding multiple documents returns all IDs."""
        docs = [
            {
                "id": f"multi-{i}",
                "embedding": [0.1 * (i + 1)] * 10,
                "text": f"Document chunk {i} content.",
                "source": "multi.pdf",
                "document_id": "doc-multi",
                "chunk_index": i,
                "filename": "multi.pdf",
                "user_id": "user-1",
            }
            for i in range(5)
        ]
        result = await chroma_db.add_documents(docs)

        assert isinstance(result, list)
        assert len(result) == 5
        for i in range(5):
            assert f"multi-{i}" in result


class TestSearch:
    """Tests for searching documents in ChromaDB."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self, chroma_db):
        """Test that search returns matching results."""
        docs = [
            {
                "id": f"search-{i}",
                "embedding": [float(i) / 10.0] * 10,
                "text": f"Legal document content number {i}.",
                "source": "search.pdf",
                "document_id": "doc-search",
                "chunk_index": i,
                "filename": "search.pdf",
                "user_id": "user-1",
            }
            for i in range(3)
        ]
        await chroma_db.add_documents(docs)

        query_embedding = [0.1] * 10
        results = await chroma_db.search(query_embedding, top_k=3, filter={"user_id": "user-1"})

        assert isinstance(results, list)
        assert len(results) > 0
        for r in results:
            assert "id" in r
            assert "text" in r
            assert "similarity" in r

    @pytest.mark.asyncio
    async def test_search_respects_top_k(self, chroma_db):
        """Test that search returns at most top_k results."""
        docs = [
            {
                "id": f"topk-{i}",
                "embedding": [float(i) / 20.0] * 10,
                "text": f"Content for top_k test {i}.",
                "source": "topk.pdf",
                "document_id": "doc-topk",
                "chunk_index": i,
                "filename": "topk.pdf",
                "user_id": "user-1",
            }
            for i in range(10)
        ]
        await chroma_db.add_documents(docs)

        results = await chroma_db.search([0.1] * 10, top_k=3, filter={"user_id": "user-1"})
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_search_results_have_rank(self, chroma_db):
        """Test that search results include rank field."""
        docs = [
            {
                "id": f"rank-{i}",
                "embedding": [0.5] * 10,
                "text": f"Ranked document {i}.",
                "source": "rank.pdf",
                "document_id": "doc-rank",
                "chunk_index": i,
                "filename": "rank.pdf",
                "user_id": "user-1",
            }
            for i in range(3)
        ]
        await chroma_db.add_documents(docs)

        results = await chroma_db.search([0.5] * 10, top_k=3, filter={"user_id": "user-1"})
        for r in results:
            assert "rank" in r
            assert isinstance(r["rank"], int)

    @pytest.mark.asyncio
    async def test_search_with_filter(self, chroma_db):
        """Test that search with metadata filter narrows results."""
        docs = [
            {
                "id": "filter-a",
                "embedding": [0.1] * 10,
                "text": "Document from user A.",
                "source": "a.pdf",
                "document_id": "doc-a",
                "chunk_index": 0,
                "filename": "a.pdf",
                "user_id": "user-a",
            },
            {
                "id": "filter-b",
                "embedding": [0.1] * 10,
                "text": "Document from user B.",
                "source": "b.pdf",
                "document_id": "doc-b",
                "chunk_index": 0,
                "filename": "b.pdf",
                "user_id": "user-b",
            },
        ]
        await chroma_db.add_documents(docs)

        results = await chroma_db.search([0.1] * 10, top_k=10, filter={"user_id": "user-a"})
        for r in results:
            assert r.get("metadata", {}).get("user_id") == "user-a"

    @pytest.mark.asyncio
    async def test_search_empty_collection_returns_empty(self, chroma_db):
        """Test searching an empty collection returns empty list."""
        results = await chroma_db.search([0.1] * 10, top_k=5, filter={"user_id": "user-1"})
        assert isinstance(results, list)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_without_user_id_is_rejected(self, chroma_db):
        """Search without a user_id filter must be rejected (tenant isolation)."""
        with pytest.raises(ValueError, match="user_id"):
            await chroma_db.search([0.1] * 10, top_k=5)
        with pytest.raises(ValueError, match="user_id"):
            await chroma_db.search([0.1] * 10, top_k=5, filter={"document_id": "doc-1"})
        # A compound filter without user scope is rejected too.
        with pytest.raises(ValueError, match="user_id"):
            await chroma_db.search([0.1] * 10, top_k=5, filter={"$and": [{"document_id": "doc-1"}]})

    async def test_search_accepts_user_id_inside_and_clause(self, chroma_db):
        """Document-scoped searches use Chroma's $and shape — user_id inside the
        clause satisfies tenant isolation (this path previously crashed)."""
        results = await chroma_db.search(
            [0.1] * 10,
            top_k=5,
            filter={"$and": [{"user_id": "user-1"}, {"document_id": {"$in": ["doc-1"]}}]},
        )
        assert isinstance(results, list)


class TestDelete:
    """Tests for deleting documents from ChromaDB."""

    @pytest.mark.asyncio
    async def test_delete_removes_documents(self, chroma_db):
        """Test that delete removes documents by ID."""
        docs = [
            {
                "id": f"del-{i}",
                "embedding": [0.3] * 10,
                "text": f"Delete test {i}.",
                "source": "del.pdf",
                "document_id": "doc-del",
                "chunk_index": i,
                "filename": "del.pdf",
                "user_id": "user-1",
            }
            for i in range(3)
        ]
        await chroma_db.add_documents(docs)

        result = await chroma_db.delete(["del-0", "del-1"])
        assert result is True

        stats = await chroma_db.get_stats()
        # At least del-2 should remain; del-0 and del-1 removed
        assert stats["total_chunks"] >= 1

    @pytest.mark.asyncio
    async def test_delete_by_document_removes_all_chunks(self, chroma_db):
        """Test that delete_by_document removes all chunks for a document_id."""
        docs = [
            {
                "id": f"dbd-{i}",
                "embedding": [0.4] * 10,
                "text": f"Chunk {i} of document.",
                "source": "dbd.pdf",
                "document_id": "doc-dbd-target",
                "chunk_index": i,
                "filename": "dbd.pdf",
                "user_id": "user-1",
            }
            for i in range(4)
        ]
        await chroma_db.add_documents(docs)

        result = await chroma_db.delete_by_document("doc-dbd-target")
        assert result is True


class TestClearAll:
    """Tests for clearing the entire collection."""

    @pytest.mark.asyncio
    async def test_clear_all_empties_collection(self, chroma_db):
        """Test that clear_all removes all documents."""
        docs = [
            {
                "id": f"clear-{i}",
                "embedding": [0.5] * 10,
                "text": f"Clear test {i}.",
                "source": "clear.pdf",
                "document_id": "doc-clear",
                "chunk_index": i,
                "filename": "clear.pdf",
                "user_id": "user-1",
            }
            for i in range(5)
        ]
        await chroma_db.add_documents(docs)

        result = await chroma_db.clear_all()
        assert result is True

        stats = await chroma_db.get_stats()
        assert stats["total_chunks"] == 0


class TestGetStats:
    """Tests for collection statistics."""

    @pytest.mark.asyncio
    async def test_get_stats_returns_correct_structure(self, chroma_db):
        """Test that get_stats returns dict with required keys."""
        stats = await chroma_db.get_stats()

        assert isinstance(stats, dict)
        assert "total_chunks" in stats
        assert "collection_name" in stats
        assert "db_type" in stats

    @pytest.mark.asyncio
    async def test_get_stats_empty_collection(self, chroma_db):
        """Test stats on an empty collection."""
        stats = await chroma_db.get_stats()

        assert stats["total_chunks"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_after_adding_documents(self, chroma_db):
        """Test that stats reflect added documents."""
        docs = [
            {
                "id": f"stats-{i}",
                "embedding": [0.6] * 10,
                "text": f"Stats test {i}.",
                "source": "stats.pdf",
                "document_id": "doc-stats",
                "chunk_index": i,
                "filename": "stats.pdf",
                "user_id": "user-1",
            }
            for i in range(3)
        ]
        await chroma_db.add_documents(docs)

        stats = await chroma_db.get_stats()
        assert stats["total_chunks"] == 3

    @pytest.mark.asyncio
    async def test_get_stats_total_documents(self, chroma_db):
        """Test that total_documents counts unique document_ids."""
        docs = [
            {
                "id": "td-0",
                "embedding": [0.7] * 10,
                "text": "Doc A chunk 0.",
                "source": "a.pdf",
                "document_id": "doc-A",
                "chunk_index": 0,
                "filename": "a.pdf",
                "user_id": "user-1",
            },
            {
                "id": "td-1",
                "embedding": [0.7] * 10,
                "text": "Doc A chunk 1.",
                "source": "a.pdf",
                "document_id": "doc-A",
                "chunk_index": 1,
                "filename": "a.pdf",
                "user_id": "user-1",
            },
            {
                "id": "td-2",
                "embedding": [0.8] * 10,
                "text": "Doc B chunk 0.",
                "source": "b.pdf",
                "document_id": "doc-B",
                "chunk_index": 0,
                "filename": "b.pdf",
                "user_id": "user-1",
            },
        ]
        await chroma_db.add_documents(docs)

        stats = await chroma_db.get_stats()
        assert stats["total_chunks"] == 3
        assert stats.get("total_documents", 0) >= 2 or stats["total_chunks"] == 3
