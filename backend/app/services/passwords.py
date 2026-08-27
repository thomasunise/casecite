"""Password hashing helpers.

Uses PBKDF2-HMAC-SHA256 with per-password random salt and constant-time verification.
Avoids runtime dependency issues with passlib/bcrypt across environments.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 600000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256."""
    if not isinstance(password, str) or not password:
        raise ValueError("Password is required")

    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)

    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(derived).decode("ascii")
    return f"{_ALGORITHM}${_ITERATIONS}${salt_b64}${hash_b64}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    """Verify plaintext password against stored PBKDF2 hash."""
    if not password or not stored_hash:
        return False

    try:
        algorithm, iterations_str, salt_b64, expected_b64 = stored_hash.split("$", 3)
        if algorithm != _ALGORITHM:
            return False

        iterations = int(iterations_str)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(expected_b64.encode("ascii"))
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)
