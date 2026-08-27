"""
Tests for at-rest document encryption (app/utils/file_crypto.py) and the
startup migration that encrypts legacy plaintext uploads.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import pytest
from app.utils import file_crypto
from app.utils.file_crypto import FileDecryptionError


class TestFileCrypto:
    def test_round_trip(self):
        data = b"%PDF-1.7 privileged client document contents"
        blob = file_crypto.encrypt_bytes(data)
        assert blob != data
        assert file_crypto.decrypt_bytes(blob) == data

    def test_ciphertext_is_marked_and_unreadable(self):
        data = b"attorney-client privileged"
        blob = file_crypto.encrypt_bytes(data)
        assert file_crypto.is_encrypted(blob)
        assert data not in blob  # plaintext must not appear in the stored blob

    def test_legacy_plaintext_passes_through(self):
        data = b"uploaded before encryption existed"
        assert not file_crypto.is_encrypted(data)
        assert file_crypto.decrypt_bytes(data) == data

    def test_nonces_are_unique_per_encryption(self):
        data = b"same input"
        assert file_crypto.encrypt_bytes(data) != file_crypto.encrypt_bytes(data)

    def test_tampered_blob_fails_closed(self):
        blob = bytearray(file_crypto.encrypt_bytes(b"do not tamper"))
        blob[-1] ^= 0x01
        with pytest.raises(FileDecryptionError):
            file_crypto.decrypt_bytes(bytes(blob))

    def test_truncated_blob_fails_closed(self):
        blob = file_crypto.encrypt_bytes(b"data")
        with pytest.raises(FileDecryptionError):
            file_crypto.decrypt_bytes(blob[: len(file_crypto.MAGIC) + 4])

    def test_empty_payload_round_trip(self):
        assert file_crypto.decrypt_bytes(file_crypto.encrypt_bytes(b"")) == b""


class TestEncryptExistingFiles:
    @pytest.fixture()
    def service_with_plaintext_doc(self, tmp_path, monkeypatch):
        """A DocumentService whose index has one doc stored as legacy plaintext."""
        from datetime import UTC, datetime
        from types import SimpleNamespace

        import app.services.documents as documents_module
        from app.models.schemas import ConnectorType, Document, DocumentStatus
        from app.services.documents import DocumentService

        # Settings is frozen; swap the module-level reference instead.
        monkeypatch.setattr(documents_module, "settings", SimpleNamespace(upload_dir=str(tmp_path)))
        service = DocumentService.__new__(DocumentService)
        service.documents = {}
        service.folders = {}

        doc = Document(
            id="doc-1",
            user_id="user-1",
            filename="brief.pdf",
            content_type="application/pdf",
            size=5,
            source=ConnectorType.LOCAL,
            status=DocumentStatus.INDEXED,
            created_at=datetime.now(UTC),
            metadata={},
        )
        service.documents[doc.id] = doc
        user_dir = tmp_path / "user-1"
        user_dir.mkdir()
        (user_dir / "doc-1.pdf").write_bytes(b"plaintext-pdf-bytes")
        return service, user_dir / "doc-1.pdf"

    def test_migrates_plaintext_and_is_idempotent(self, service_with_plaintext_doc):
        service, path = service_with_plaintext_doc

        result = service.encrypt_existing_files()
        assert result == {"migrated": 1, "failed": 0}
        on_disk = path.read_bytes()
        assert file_crypto.is_encrypted(on_disk)
        assert file_crypto.decrypt_bytes(on_disk) == b"plaintext-pdf-bytes"

        # Second run must be a no-op (no double encryption).
        assert service.encrypt_existing_files() == {"migrated": 0, "failed": 0}
        assert file_crypto.decrypt_bytes(path.read_bytes()) == b"plaintext-pdf-bytes"

    @pytest.mark.asyncio
    async def test_read_file_decrypts(self, service_with_plaintext_doc):
        service, path = service_with_plaintext_doc
        service.encrypt_existing_files()
        assert await service.read_file(str(path)) == b"plaintext-pdf-bytes"
