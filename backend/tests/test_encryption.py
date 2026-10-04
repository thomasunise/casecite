"""Tests for backend/app/services/encryption.py"""

import os

import pytest
from app.services.encryption import EncryptionService
from cryptography.exceptions import InvalidTag


@pytest.fixture
def enc_service():
    return EncryptionService()


class TestEncryptionServiceBytes:
    """Tests for encrypt/decrypt with raw bytes."""

    def test_encrypt_decrypt_round_trip(self, enc_service):
        plaintext = b"Hello, CaseCite!"
        ciphertext = enc_service.encrypt(plaintext)
        assert ciphertext != plaintext
        assert enc_service.decrypt(ciphertext) == plaintext

    def test_encrypt_produces_different_ciphertext_each_call(self, enc_service):
        plaintext = b"same input"
        ct1 = enc_service.encrypt(plaintext)
        ct2 = enc_service.encrypt(plaintext)
        # AES-GCM uses random nonce so ciphertext should differ
        assert ct1 != ct2

    def test_tamper_detection(self, enc_service):
        ciphertext = enc_service.encrypt(b"sensitive data")
        # Flip a byte near the end (inside the auth tag region)
        tampered = bytearray(ciphertext)
        tampered[-1] ^= 0xFF
        tampered = bytes(tampered)
        with pytest.raises((InvalidTag, Exception)):
            enc_service.decrypt(tampered)

    def test_encrypt_empty_bytes(self, enc_service):
        ciphertext = enc_service.encrypt(b"")
        assert enc_service.decrypt(ciphertext) == b""


class TestEncryptionServiceStrings:
    """Tests for encrypt_string/decrypt_string."""

    def test_string_round_trip(self, enc_service):
        plaintext = "Attorney-client privileged communication"
        encrypted = enc_service.encrypt_string(plaintext)
        assert isinstance(encrypted, str)
        assert encrypted != plaintext
        assert enc_service.decrypt_string(encrypted) == plaintext

    def test_string_unicode_round_trip(self, enc_service):
        plaintext = "Legal brief with unicode: \u00a7 \u00b6 \u2014 \u201c \u201d"
        encrypted = enc_service.encrypt_string(plaintext)
        assert enc_service.decrypt_string(encrypted) == plaintext


class TestPasswordHashing:
    """Tests for hash_password and verify_password."""

    def test_hash_password_returns_string(self, enc_service):
        hashed = enc_service.hash_password("SecureP@ss123")
        assert isinstance(hashed, str)
        assert hashed != "SecureP@ss123"

    def test_verify_password_correct(self, enc_service):
        password = "SecureP@ss123"
        hashed = enc_service.hash_password(password)
        assert enc_service.verify_password(password, hashed) is True

    def test_verify_password_wrong(self, enc_service):
        hashed = enc_service.hash_password("CorrectPassword1!")
        assert enc_service.verify_password("WrongPassword1!", hashed) is False

    def test_hash_password_unique_salts(self, enc_service):
        password = "SamePassword1!"
        h1 = enc_service.hash_password(password)
        h2 = enc_service.hash_password(password)
        # bcrypt/pbkdf2 produces different hashes due to random salt
        assert h1 != h2


class TestDecryptStringErrors:
    """decrypt_string must raise the documented ValueError, never InvalidTag."""

    def test_wrong_key_raises_value_error(self, enc_service):

        token = enc_service.encrypt_string("secret")
        other = EncryptionService()
        other._master_key = os.urandom(32)
        other._previous_keys = []
        with pytest.raises(ValueError, match="Failed to decrypt"):
            other.decrypt_string(token)

    def test_tampered_ciphertext_raises_value_error(self, enc_service):
        import base64

        raw = bytearray(base64.b64decode(enc_service.encrypt_string("secret")))
        raw[-1] ^= 0xFF
        with pytest.raises(ValueError, match="Failed to decrypt"):
            enc_service.decrypt_string(base64.b64encode(bytes(raw)).decode("ascii"))

    def test_garbage_raises_value_error(self, enc_service):
        with pytest.raises(ValueError, match="Failed to decrypt"):
            enc_service.decrypt_string("not-base64-!!")
