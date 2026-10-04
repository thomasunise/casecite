"""
AES-256-GCM encryption for uploaded documents at rest.

Uploaded client files are privileged legal material and must not sit on disk in
plaintext. Every file written by DocumentService is wrapped as:

    MAGIC (8 bytes) || nonce (12 bytes) || AES-256-GCM ciphertext+tag

The key is an HKDF subkey of SECRET_KEY (purpose "file-at-rest"), so it is
domain-separated from the JWT/CSRF/field-encryption keys. The MAGIC header is
bound as GCM associated data, so a truncated or re-headered blob fails
authentication instead of decrypting garbage.

``decrypt_bytes`` transparently passes through blobs without the header, so
files uploaded before this feature (legacy plaintext) keep working; the startup
migration in DocumentService.encrypt_existing_files() rewrites them encrypted.
"""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.utils.keys import derive_subkey

MAGIC = b"PARAENC1"
_NONCE_LEN = 12


class FileDecryptionError(Exception):
    """An encrypted file failed authentication (corrupted or wrong SECRET_KEY)."""


@lru_cache(maxsize=1)
def _aesgcm() -> AESGCM:
    return AESGCM(derive_subkey("file-at-rest"))


def is_encrypted(data: bytes) -> bool:
    """True if the blob carries the encrypted-file header."""
    return data[: len(MAGIC)] == MAGIC


def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt raw file content for storage on disk."""
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = _aesgcm().encrypt(nonce, data, MAGIC)
    return MAGIC + nonce + ciphertext


def decrypt_bytes(data: bytes) -> bytes:
    """Return plaintext file content from a stored blob.

    Blobs without the MAGIC header are legacy plaintext files and are returned
    unchanged. Raises FileDecryptionError if an encrypted blob fails GCM
    authentication.
    """
    if not is_encrypted(data):
        return data
    body = data[len(MAGIC) :]
    if len(body) <= _NONCE_LEN:
        raise FileDecryptionError("Encrypted file is truncated")
    nonce, ciphertext = body[:_NONCE_LEN], body[_NONCE_LEN:]
    try:
        return _aesgcm().decrypt(nonce, ciphertext, MAGIC)
    except InvalidTag as e:
        raise FileDecryptionError(
            "Encrypted file failed authentication (corrupted, or SECRET_KEY changed)"
        ) from e
