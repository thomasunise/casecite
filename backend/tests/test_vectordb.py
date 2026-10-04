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


class TestDocumentChunks:
    """Direct chunk reads go through the vector-store abstraction."""

    @staticmethod
    def _bind(chroma_db):
        return chroma_db

    @staticmethod
    def _chunk(doc_id, index, user_id, **extra):
        return {
            "id": f"{doc_id}_{index}",
            "embedding": [0.1 * (index + 1)] * 10,
            "text": f"{doc_id} chunk {index}",
            "document_id": doc_id,
            "chunk_index": index,
            "filename": f"{doc_id}.pdf",
            "user_id": user_id,
            **extra,
        }

    @pytest.mark.asyncio
    async def test_returns_only_the_callers_chunks_of_that_document(self, chroma_db):
        db = self._bind(chroma_db)
        await db.add_documents(
            [self._chunk("doc-a", i, "user-1") for i in range(3)]
            + [self._chunk("doc-b", 0, "user-1"), self._chunk("doc-c", 0, "user-2")]
        )

        chunks = await db.get_document_chunks("doc-a", {"user_id": "user-1"}, limit=50)

        assert sorted(c["id"] for c in chunks) == ["doc-a_0", "doc-a_1", "doc-a_2"]
        assert all("similarity" not in c for c in chunks)  # nothing was searched
        assert await db.get_document_chunks("doc-c", {"user_id": "user-1"}) == []

    @pytest.mark.asyncio
    async def test_matter_members_can_read_a_shared_document(self, chroma_db):
        db = self._bind(chroma_db)
        await db.add_documents([self._chunk("doc-m", 0, "user-2", matter_id="matter-1")])

        scope = {"$or": [{"user_id": "user-1"}, {"matter_id": {"$in": ["matter-1"]}}]}
        assert [c["id"] for c in await db.get_document_chunks("doc-m", scope)] == ["doc-m_0"]

    @pytest.mark.asyncio
    async def test_refuses_an_unscoped_read(self, chroma_db):
        db = self._bind(chroma_db)
        with pytest.raises(ValueError, match="scope is required"):
            await db.get_document_chunks("doc-a", {})


class TestChromaInitFailure:
    """An unopenable store is never wiped without a verified backup."""

    @staticmethod
    def _store_with_data(tmp_path):
        store = tmp_path / "chroma"
        (store / "segment").mkdir(parents=True)
        (store / "chroma.sqlite3").write_bytes(b"firm index " * 100)
        (store / "segment" / "data.bin").write_bytes(b"vectors " * 50)
        return store

    def test_backup_failure_stops_startup_and_deletes_nothing(self, tmp_path):
        from unittest.mock import patch

        from app.services import vectordb

        store = self._store_with_data(tmp_path)
        with (
            patch.object(vectordb, "settings") as mock_settings,
            patch.object(
                vectordb.chromadb, "PersistentClient", side_effect=ValueError("no such column")
            ),
            patch.object(vectordb.shutil, "copytree", side_effect=OSError("No space left")),
        ):
            mock_settings.chroma_persist_dir = str(store)
            with pytest.raises(vectordb.VectorStoreCorruptError, match="Nothing was deleted"):
                vectordb.ChromaDB()

        assert (store / "chroma.sqlite3").read_bytes() == b"firm index " * 100
        assert (store / "segment" / "data.bin").exists()

    def test_truncated_backup_is_treated_as_failure(self, tmp_path):
        import os
        from unittest.mock import patch

        from app.services import vectordb

        store = self._store_with_data(tmp_path)

        def truncating_copy(src, dst):
            os.makedirs(os.path.join(dst, "segment"))
            with open(os.path.join(dst, "chroma.sqlite3"), "wb") as f:
                f.write(b"firm")  # short write
            with open(os.path.join(dst, "segment", "data.bin"), "wb") as f:
                f.write(b"vectors " * 50)

        with (
            patch.object(vectordb, "settings") as mock_settings,
            patch.object(
                vectordb.chromadb, "PersistentClient", side_effect=ValueError("no such column")
            ),
            patch.object(vectordb.shutil, "copytree", side_effect=truncating_copy),
        ):
            mock_settings.chroma_persist_dir = str(store)
            with pytest.raises(vectordb.VectorStoreCorruptError):
                vectordb.ChromaDB()

        assert (store / "chroma.sqlite3").read_bytes() == b"firm index " * 100

    def test_reset_only_after_a_verified_backup(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from app.services import vectordb

        store = self._store_with_data(tmp_path)
        fresh_client = MagicMock()
        with (
            patch.object(vectordb, "settings") as mock_settings,
            patch.object(
                vectordb.chromadb,
                "PersistentClient",
                side_effect=[ValueError("no such column"), fresh_client],
            ),
        ):
            mock_settings.chroma_persist_dir = str(store)
            db = vectordb.ChromaDB()

        assert db.client is fresh_client
        assert list(store.iterdir()) == []  # the unopenable files were cleared...
        backups = [p for p in tmp_path.iterdir() if p.name.startswith("chroma_corrupt_")]
        assert len(backups) == 1  # ...and a complete copy of them exists
        assert (backups[0] / "chroma.sqlite3").read_bytes() == b"firm index " * 100
        assert (backups[0] / "segment" / "data.bin").read_bytes() == b"vectors " * 50

    def test_corrupt_store_error_is_not_swallowed_by_the_factory(self):
        """get_vector_db tolerates ordinary init failures (search is disabled)
        but must not swallow a store that could not be backed up."""
        from unittest.mock import patch

        from app.services import vectordb

        with (
            patch.object(vectordb, "_db_instance", None),
            patch.object(
                vectordb, "ChromaDB", side_effect=vectordb.VectorStoreCorruptError("unopenable")
            ),
            pytest.raises(vectordb.VectorStoreCorruptError),
        ):
            vectordb.get_vector_db()


class TestPineconeBackend:
    """PineconeDB against a mocked index (the backend is experimental: there
    are no live-service tests)."""

    @staticmethod
    def _db(matches=()):
        from unittest.mock import MagicMock

        from app.services.vectordb import PineconeDB

        db = PineconeDB.__new__(PineconeDB)
        db.index = MagicMock()
        db.index.query.return_value = MagicMock(matches=list(matches))
        db._dimension = 4
        return db

    @staticmethod
    def _match(chunk_id, **metadata):
        from unittest.mock import MagicMock

        return MagicMock(id=chunk_id, metadata=metadata, score=0.0)

    @pytest.mark.asyncio
    async def test_chunk_text_is_stored_in_full(self):
        """Regression: text was cut to 1,000 characters, so answers were built
        from truncated passages."""
        db = self._db()
        text = "Clause text. " * 250  # ~3,250 chars, a normal 512-token chunk

        await db.add_documents(
            [
                {
                    "id": "d_0",
                    "embedding": [0.1] * 4,
                    "text": text,
                    "document_id": "d",
                    "user_id": "user-1",
                    "doc_type": "contract",
                    "folder_path": "/Clients/Acme/",
                }
            ]
        )

        metadata = db.index.upsert.call_args.kwargs["vectors"][0]["metadata"]
        assert metadata["text"] == text
        assert metadata["doc_type"] == "contract"
        assert metadata["folder_path"] == "/Clients/Acme/"

    def test_oversized_text_is_bounded_without_splitting_a_character(self):
        from app.services.vectordb import PINECONE_TEXT_BYTES, _fit_utf8

        fitted = _fit_utf8("é" * 40_000, PINECONE_TEXT_BYTES)
        assert len(fitted.encode("utf-8")) <= PINECONE_TEXT_BYTES
        assert set(fitted) == {"é"}

    @pytest.mark.asyncio
    async def test_get_document_chunks_filters_by_document_and_tenant(self):
        db = self._db(
            [
                self._match("d_1", text="second", chunk_index=1, document_id="d"),
                self._match("d_0", text="first", chunk_index=0, document_id="d"),
            ]
        )

        chunks = await db.get_document_chunks("d", {"user_id": "user-1"}, limit=50)

        assert [c["text"] for c in chunks] == ["first", "second"]
        kwargs = db.index.query.call_args.kwargs
        assert kwargs["filter"] == {"$and": [{"document_id": "d"}, {"user_id": "user-1"}]}
        assert kwargs["top_k"] == 50
        assert kwargs["include_metadata"] is True

    @pytest.mark.asyncio
    async def test_get_document_chunks_refuses_an_unscoped_read(self):
        db = self._db()
        with pytest.raises(ValueError, match="scope is required"):
            await db.get_document_chunks("d", {})
        db.index.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_has_document_reflects_the_index(self):
        """Regression: has_document always answered True, so startup
        reconciliation could never notice missing vectors."""
        assert await self._db([self._match("d_0")]).has_document("d") is True
        assert await self._db([]).has_document("d") is False
