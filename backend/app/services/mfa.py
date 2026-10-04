"""
TOTP multi-factor authentication service.

Provides RFC-6238 TOTP enrollment/verification and single-use recovery codes for
password-login accounts. Secrets are encrypted at rest (via the shared
encryption service); recovery codes are stored only as SHA-256 hashes.

A short-lived, signed "MFA challenge" token bridges the two login steps: after a
correct password, the login endpoint returns a challenge instead of full tokens,
and /auth/mfa/verify exchanges (challenge + TOTP/recovery code) for real tokens.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from app.services.encryption import encryption_service
from app.utils.keys import derive_subkey

ISSUER_NAME = "CaseCite"
RECOVERY_CODE_COUNT = 10
CHALLENGE_TTL_SECONDS = 300  # 5 minutes to complete the second factor


# ---------------------------------------------------------------------------
# TOTP secret management
# ---------------------------------------------------------------------------
def generate_secret() -> str:
    """Generate a new base32 TOTP secret."""
    import pyotp

    return pyotp.random_base32()


def provisioning_uri(secret: str, account_email: str) -> str:
    """Build the otpauth:// URI an authenticator app scans."""
    import pyotp

    return pyotp.TOTP(secret).provisioning_uri(name=account_email, issuer_name=ISSUER_NAME)


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code (±1 window for clock skew)."""
    if not secret or not code:
        return False
    import pyotp

    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)


# A TOTP code stays valid for its 30-second step plus one step either side
# (valid_window=1), so a used code is remembered a little longer than that.
_TOTP_REUSE_TTL_SECONDS = 120

# In-memory fallback for used-code tracking (dev, or if Redis is down).
# Maps sha256(user_id:code) -> expiry epoch; pruned lazily on access.
_used_totp_codes: dict[str, float] = {}


def verify_totp_once(user_id: str, secret: str, code: str, now: float | None = None) -> bool:
    """Verify a TOTP code and spend it: the same code is never accepted twice.

    RFC 6238 requires that a verifier not accept a second use of an OTP. Without
    this, a code observed once (shoulder-surfed, phished in real time, or read
    from a log) can be replayed for the rest of its ~90-second validity.
    """
    if not verify_totp(secret, code):
        return False
    normalized = code.strip().replace(" ", "")
    marker = hashlib.sha256(f"{user_id}:{normalized}".encode()).hexdigest()
    current = now if now is not None else time.time()

    from app.redis_utils import require_redis

    client = require_redis()
    if client is not None:
        try:
            # SET NX succeeds only the first time this (user, code) is seen.
            return bool(
                client.set(f"mfa_totp_used:{marker}", "1", nx=True, ex=_TOTP_REUSE_TTL_SECONDS)
            )
        except Exception:  # fall through to in-memory on any Redis error
            pass

    for key, exp in list(_used_totp_codes.items()):
        if exp < current:
            _used_totp_codes.pop(key, None)
    if marker in _used_totp_codes:
        return False
    _used_totp_codes[marker] = current + _TOTP_REUSE_TTL_SECONDS
    return True


def encrypt_secret(secret: str) -> str:
    return encryption_service.encrypt_string(secret)


def decrypt_secret(encrypted: str) -> str:
    return encryption_service.decrypt_string(encrypted)


# ---------------------------------------------------------------------------
# Recovery codes
# ---------------------------------------------------------------------------
def _hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().replace("-", "").encode()).hexdigest()


def generate_recovery_codes(n: int = RECOVERY_CODE_COUNT) -> tuple[list[str], list[str]]:
    """Return (plaintext_codes, hashed_codes). Show plaintext to the user once."""
    codes = [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(n)]
    return codes, [_hash_recovery_code(c) for c in codes]


def consume_recovery_code(code: str, hashed_codes: list[str]) -> tuple[bool, list[str]]:
    """If ``code`` matches a stored hash, return (True, remaining_hashes)."""
    if not code or not hashed_codes:
        return False, hashed_codes
    target = _hash_recovery_code(code)
    for h in hashed_codes:
        if hmac.compare_digest(h, target):
            return True, [x for x in hashed_codes if x != h]
    return False, hashed_codes


# ---------------------------------------------------------------------------
# MFA challenge token (signed, short-lived, single-use; HMAC over
# user_id + expiry + nonce). The nonce makes each challenge individually
# revocable so a completed challenge cannot be replayed for fresh tokens.
# ---------------------------------------------------------------------------
def _challenge_key() -> bytes:
    return derive_subkey("mfa-challenge")


# In-memory fallback for consumed-challenge tracking (dev/demo, or if Redis is
# down). Maps nonce -> expiry epoch; pruned lazily on access.
_consumed_challenges: dict[str, float] = {}


def create_challenge_token(user_id: str, now: float | None = None) -> str:
    """Create a signed, single-use challenge binding the user for CHALLENGE_TTL_SECONDS."""
    expires = int((now if now is not None else time.time()) + CHALLENGE_TTL_SECONDS)
    nonce = secrets.token_hex(16)
    payload = f"{user_id}:{expires}:{nonce}"
    sig = hmac.new(_challenge_key(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def _split_challenge(token: str) -> tuple[str, int, str] | None:
    """Validate signature + expiry; return (user_id, expires, nonce) or None."""
    if not token or token.count(":") != 3:
        return None
    user_id, expires_str, nonce, sig = token.split(":")
    payload = f"{user_id}:{expires_str}:{nonce}"
    expected = hmac.new(_challenge_key(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        expires = int(expires_str)
    except ValueError:
        return None
    return user_id, expires, nonce


def verify_challenge_token(token: str, now: float | None = None) -> str | None:
    """Return the user_id if the challenge is valid, unexpired, and not consumed."""
    parsed = _split_challenge(token)
    if not parsed:
        return None
    user_id, expires, nonce = parsed
    current = now if now is not None else time.time()
    if current > expires:
        return None
    if _is_challenge_consumed(nonce, current):
        return None
    return user_id


def consume_challenge_token(token: str, now: float | None = None) -> bool:
    """Mark a challenge single-use-spent. Returns False if already consumed/invalid.

    Consumed atomically in Redis (SET NX) when available so a completed challenge
    cannot be replayed to mint a second set of tokens; falls back to an in-memory
    set in dev/demo or if Redis is unreachable.
    """
    parsed = _split_challenge(token)
    if not parsed:
        return False
    _user_id, expires, nonce = parsed
    current = now if now is not None else time.time()
    if current > expires:
        return False
    ttl = max(1, int(expires - current))

    from app.redis_utils import require_redis

    client = require_redis()
    if client is not None:
        try:
            # SET NX succeeds only if the nonce was never seen -> first (only) use.
            return bool(client.set(f"mfa_challenge_used:{nonce}", "1", nx=True, ex=ttl))
        except Exception:  # fall through to in-memory on any Redis error
            pass

    # In-memory fallback: prune expired, then claim the nonce if unseen.
    for n, exp in list(_consumed_challenges.items()):
        if exp < current:
            _consumed_challenges.pop(n, None)
    if nonce in _consumed_challenges:
        return False
    _consumed_challenges[nonce] = expires
    return True


def _is_challenge_consumed(nonce: str, now: float) -> bool:
    from app.redis_utils import get_redis

    client = get_redis()
    if client is not None:
        try:
            return client.exists(f"mfa_challenge_used:{nonce}") == 1
        except Exception:
            pass
    exp = _consumed_challenges.get(nonce)
    return exp is not None and exp >= now
