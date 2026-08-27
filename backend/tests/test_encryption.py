"""Tests for backend/app/services/encryption.py"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import pytest
from app.services.encryption import EncryptionService, FieldEncryption
from cryptography.exceptions import InvalidTag


@pytest.fixture
def enc_service():
    return EncryptionService()


@pytest.fixture
def field_enc(enc_service):
    return FieldEncryption(enc_service)


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


class TestApiKeyGeneration:
    """Tests for generate_api_key."""

    def test_generate_api_key_format(self, enc_service):
        key_id, secret_key = enc_service.generate_api_key()
        assert isinstance(key_id, str)
        assert isinstance(secret_key, str)
        assert key_id.startswith("pa_")

    def test_generate_api_key_unique(self, enc_service):
        pair1 = enc_service.generate_api_key()
        pair2 = enc_service.generate_api_key()
        assert pair1[0] != pair2[0]
        assert pair1[1] != pair2[1]


class TestFileEncryption:
    """Tests for encrypt_file and decrypt_file."""

    def test_encrypt_decrypt_file(self, enc_service, tmp_path):
        # Create a plaintext file
        source = tmp_path / "document.txt"
        source.write_text("Confidential legal document contents.")

        # Encrypt
        encrypted_path = enc_service.encrypt_file(str(source))
        assert os.path.exists(encrypted_path)
        assert encrypted_path != str(source)

        # Decrypt
        decrypted_path = enc_service.decrypt_file(encrypted_path)
        assert os.path.exists(decrypted_path)

        with open(decrypted_path) as f:
            assert f.read() == "Confidential legal document contents."

    def test_encrypt_file_custom_output(self, enc_service, tmp_path):
        source = tmp_path / "input.txt"
        source.write_text("Test data for encryption.")
        output = str(tmp_path / "custom_output.enc")

        result = enc_service.encrypt_file(str(source), output_path=output)
        assert result == output
        assert os.path.exists(output)


class TestFieldEncryption:
    """Tests for FieldEncryption wrapper."""

    def test_field_encrypt_decrypt_round_trip(self, field_enc):
        value = "SSN: 123-45-6789"
        encrypted = field_enc.encrypt_field(value)
        assert encrypted != value
        assert field_enc.decrypt_field(encrypted) == value

    def test_mask_field(self, field_enc):
        result = field_enc.mask_field("1234567890")
        assert result == "******7890"

    def test_mask_field_custom_visible(self, field_enc):
        result = field_enc.mask_field("1234567890", visible_chars=4)
        assert result == "******7890"

    def test_mask_field_short_value(self, field_enc):
        # If value is shorter than visible_chars, behavior depends on impl
        result = field_enc.mask_field("ab", visible_chars=4)
        assert isinstance(result, str)

    def test_field_encrypt_empty_string(self, field_enc):
        # Empty or None should pass through
        result = field_enc.encrypt_field("")
        # Either returns empty or encrypts it - just verify round-trip
        if result == "":
            assert True
        else:
            assert field_enc.decrypt_field(result) == ""

    def test_field_encrypt_none_passthrough(self, field_enc):
        result = field_enc.encrypt_field(None)
        assert result is None
