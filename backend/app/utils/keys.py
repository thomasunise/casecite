"""
Domain-separated key derivation.

The single ``SECRET_KEY`` previously signed JWTs, signed CSRF tokens, and (via a
separate salt) derived the data-encryption master key — so leaking any one usage
compromised all of them. We derive a distinct subkey per purpose with HKDF, so a
leaked *derived* key (e.g. the JWT signing key) cannot be reversed to recover
SECRET_KEY or any other purpose's key.

The data-encryption master key intentionally keeps its existing derivation
(PBKDF2 over SECRET_KEY + ENCRYPTION_SALT) so previously-encrypted data still
decrypts. JWT and CSRF move to derived subkeys; the one-time effect on deploy is
that existing sessions/CSRF tokens are invalidated (users re-login once).
"""

from __future__ import annotations

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings


def derive_subkey(purpose: str, length: int = 32) -> bytes:
    """Derive a purpose-specific key from SECRET_KEY via HKDF-SHA256.

    ``purpose`` is bound into the HKDF ``info`` so different purposes yield
    independent keys. Same SECRET_KEY + same purpose always yields the same key.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=None,
        # "para" is the pre-rename brand label; it is baked into every derived
        # key, so changing it would invalidate all existing encrypted data.
        info=f"para:{purpose}".encode(),
    )
    return hkdf.derive(settings.secret_key.encode())
