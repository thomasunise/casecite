"""
Encryption Service

Provides:
- Data encryption at rest (AES-256-GCM)
- Key management
- Secure key derivation
"""

import base64
import logging
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings

logger = logging.getLogger(__name__)


class EncryptionService:
    """
    AES-256-GCM encryption for data at rest.

    In production, use:
    - Azure Key Vault for key management
    - Hardware Security Module (HSM) for key storage
    """

    def __init__(self):
        # Derive encryption key from secret + per-deployment salt
        # Salt is set via ENCRYPTION_SALT environment variable
        encryption_salt = getattr(settings, "encryption_salt", None)
        if not encryption_salt:
            raise RuntimeError(
                "ENCRYPTION_SALT environment variable is required. "
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )

        self._master_key = self._derive_key(
            settings.secret_key.encode(),
            encryption_salt.encode() if isinstance(encryption_salt, str) else encryption_salt,
        )

        # Key rotation support: derive keys from previous salts so data
        # encrypted before rotation can still be decrypted after a restart.
        # Set ENCRYPTION_SALT_PREVIOUS=old_salt1,old_salt2 in .env
        self._previous_keys: list[bytes] = []
        previous_salts = getattr(settings, "encryption_salt_previous", "") or ""
        if previous_salts:
            secret = settings.secret_key.encode()
            for salt_str in previous_salts.split(","):
                salt_str = salt_str.strip()
                if salt_str:
                    self._previous_keys.append(self._derive_key(secret, salt_str.encode()))
            if self._previous_keys:
                logger.info(
                    f"Loaded {len(self._previous_keys)} previous encryption key(s) for rotation support."
                )

    def _derive_key(self, password: bytes, salt: bytes) -> bytes:
        """Derive a 256-bit key using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bits
            salt=salt,
            iterations=100000,
            backend=default_backend(),
        )
        return kdf.derive(password)

    def _derive_per_record_key(self, salt: bytes, master_key: bytes | None = None) -> bytes:
        """Derive a per-record key using HKDF from a master key."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            # Pre-rename brand label baked into every record key — changing it
            # would make all existing encrypted records undecryptable.
            info=b"para-record-encryption",
            backend=default_backend(),
        )
        return hkdf.derive(master_key or self._master_key)

    # Version byte for new per-record-salt format
    _V1_PREFIX = b"\x01"

    def encrypt(self, plaintext: bytes) -> bytes:
        """
        Encrypt data using AES-256-GCM with per-record salt.

        New format: version(1) + salt(16) + nonce(12) + ciphertext + tag
        """
        salt = secrets.token_bytes(16)
        record_key = self._derive_per_record_key(salt)
        nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(record_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return self._V1_PREFIX + salt + nonce + ciphertext

    def decrypt(self, ciphertext: bytes) -> bytes:
        """
        Decrypt data encrypted with encrypt().

        Auto-detects format: v1 prefix -> per-record salt; otherwise -> legacy.
        Raises: cryptography.exceptions.InvalidTag if tampered
        """
        if ciphertext[:1] == self._V1_PREFIX:
            # New format: version(1) + salt(16) + nonce(12) + ciphertext
            record_salt = ciphertext[1:17]
            nonce = ciphertext[17:29]
            actual_ciphertext = ciphertext[29:]

            # Try current master key first, then previous keys
            keys_to_try = [self._master_key, *self._previous_keys]
            last_exc: Exception | None = None
            for master_key in keys_to_try:
                try:
                    record_key = self._derive_per_record_key(record_salt, master_key)
                    aesgcm = AESGCM(record_key)
                    return aesgcm.decrypt(nonce, actual_ciphertext, None)
                except (InvalidTag, ValueError, TypeError, OverflowError) as exc:
                    last_exc = exc
                    continue
            raise last_exc  # All keys exhausted
        else:
            # Legacy format: nonce(12) + ciphertext (uses master key directly)
            logger.warning(
                "Decrypting legacy-format ciphertext — migrate this record to the "
                "v1 per-record-salt format for improved security."
            )
            nonce = ciphertext[:12]
            actual_ciphertext = ciphertext[12:]

            # Try current master key first, then fall back to previous keys
            # so that data encrypted before a key rotation can still be read.
            keys_to_try = [self._master_key, *reversed(self._previous_keys)]
            last_exc: Exception | None = None
            for key in keys_to_try:
                try:
                    aesgcm = AESGCM(key)
                    return aesgcm.decrypt(nonce, actual_ciphertext, None)
                except (
                    InvalidTag,
                    ValueError,
                    TypeError,
                    OverflowError,
                ) as exc:  # Try next key on decrypt failure
                    last_exc = exc
                    continue
            raise last_exc  # All keys exhausted

    def encrypt_string(self, plaintext: str) -> str:
        """Encrypt a string and return base64-encoded result."""
        encrypted = self.encrypt(plaintext.encode("utf-8"))
        return base64.b64encode(encrypted).decode("ascii")

    def decrypt_string(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded ciphertext string."""
        try:
            encrypted = base64.b64decode(ciphertext.encode("ascii"))
            decrypted = self.decrypt(encrypted)
            return decrypted.decode("utf-8")
        except (ValueError, TypeError, UnicodeDecodeError, OverflowError):
            raise ValueError(
                "Failed to decrypt data. The key may have changed or data is corrupted."
            )

    def hash_password(self, password: str) -> str:
        """Hash a password for storage.

        Delegates to the canonical password module (PBKDF2-HMAC-SHA256, 600k
        iterations, versioned format). This method previously used a weaker,
        unversioned 100k-iteration derivation with a misleading "Argon2id"
        docstring; it now shares the same strong implementation used for real
        auth so there is no weak alternative path.
        """
        from app.services import passwords

        return passwords.hash_password(password)

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against a hash produced by :meth:`hash_password`."""
        from app.services import passwords

        return passwords.verify_password(password, hashed)

    def generate_api_key(self) -> tuple[str, str]:
        """
        Generate an API key pair.
        Returns: (key_id, secret_key)
        """
        key_id = f"pa_{secrets.token_urlsafe(8)}"
        secret_key = secrets.token_urlsafe(32)
        return key_id, secret_key

    def encrypt_file(self, file_path: str, output_path: str = None) -> str:
        """Encrypt a file at rest."""
        output_path = output_path or file_path + ".enc"

        with open(file_path, "rb") as f:
            plaintext = f.read()

        encrypted = self.encrypt(plaintext)

        with open(output_path, "wb") as f:
            f.write(encrypted)

        return output_path

    def decrypt_file(self, file_path: str, output_path: str = None) -> str:
        """Decrypt an encrypted file."""
        if output_path is None:
            output_path = file_path.rsplit(".enc", 1)[0]

        with open(file_path, "rb") as f:
            ciphertext = f.read()

        decrypted = self.decrypt(ciphertext)

        with open(output_path, "wb") as f:
            f.write(decrypted)

        return output_path


class FieldEncryption:
    """
    Field-level encryption for sensitive database fields.

    Use for:
    - SSN, Tax ID
    - Financial data
    - Personal health information
    """

    def __init__(self, encryption_service: EncryptionService):
        self.crypto = encryption_service

    def encrypt_field(self, value: str) -> str:
        """Encrypt a field value."""
        if not value:
            return value
        return self.crypto.encrypt_string(value)

    def decrypt_field(self, value: str) -> str:
        """Decrypt a field value."""
        if not value:
            return value
        return self.crypto.decrypt_string(value)

    def mask_field(self, value: str, visible_chars: int = 4) -> str:
        """Mask a field value for display (e.g., SSN: ***-**-1234)."""
        if not value or len(value) <= visible_chars:
            return "*" * len(value) if value else ""

        masked_len = len(value) - visible_chars
        return "*" * masked_len + value[-visible_chars:]


# Global encryption service
encryption_service = EncryptionService()
field_encryption = FieldEncryption(encryption_service)
