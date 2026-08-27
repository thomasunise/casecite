"""
Shared Key Storage Service

Provides encrypted key storage/retrieval used by both the user_keys router
and the UserAPIKeys service (for server-side BYOK fallback).

Storage model
-------------
Per-user keys are persisted to an encrypted file on the data volume
(``data/.user_keys.json``) so they survive restarts, re-logins and redeploys
(as long as the data dir is on a persistent volume) WITHOUT requiring Redis.
This mirrors how instance-wide secrets persist.

Redis, when configured, is used only as a fast read-through cache. It is never
the source of truth, so a missing/unavailable Redis no longer causes keys to
"vanish" — previously, in production without Redis, saves failed closed and
reads returned empty, so BYOK keys never persisted at all.

All values are encrypted at rest with the shared ``encryption_service`` (the
same key used for instance secrets), so the on-disk file contains only
ciphertext.
"""

import json
import logging
import os
import threading
from pathlib import Path

from app.config import settings
from app.redis_utils import RedisError, get_redis
from app.services.encryption import encryption_service

logger = logging.getLogger(__name__)

# Redis cache TTL (cache only — the file store is permanent).
_CACHE_TTL_SECONDS = 24 * 3600

# Durable, encrypted, on-disk store: { user_id: encrypted_blob }
_DATA_DIR = Path(settings.upload_dir).parent
_KEYS_FILE = _DATA_DIR / ".user_keys.json"

# Guards read-modify-write of the file within this process.
_file_lock = threading.Lock()


def _load_store() -> dict[str, str]:
    """Load the {user_id: encrypted_blob} map from disk (empty on any error)."""
    try:
        if _KEYS_FILE.exists():
            return json.loads(_KEYS_FILE.read_text())
    except (OSError, ValueError, json.JSONDecodeError) as e:
        logger.warning("Could not read user key store %s: %s", _KEYS_FILE, e)
    return {}


def _write_store(store: dict[str, str]) -> None:
    """Atomically persist the store to disk with owner-only permissions."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _KEYS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(store))
    # Restrict to owner-only before publishing — this file holds every user's
    # (encrypted) BYOK keys, so it must not be world/group-readable. Matches the
    # 0600 convention used for .instance_secrets.json and revoked_tokens.jsonl.
    # No-op on Windows; effective on the Linux data volume used in production.
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, _KEYS_FILE)
    try:
        os.chmod(_KEYS_FILE, 0o600)
    except OSError:
        pass


def get_user_keys(user_id: str) -> dict[str, str]:
    """Get decrypted user keys. Redis cache first, then the durable file store."""
    # Fast path: Redis cache.
    redis_client = get_redis()
    if redis_client:
        try:
            data = redis_client.get(f"user_keys:{user_id}")
            if data:
                return json.loads(encryption_service.decrypt_string(data))
        except (RedisError, ValueError, KeyError, OSError, RuntimeError) as e:
            logger.warning(f"Failed to read user keys from Redis cache: {e}")

    # Source of truth: the durable file store.
    with _file_lock:
        encrypted = _load_store().get(user_id)
    if not encrypted:
        return {}
    try:
        keys = json.loads(encryption_service.decrypt_string(encrypted))
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to decrypt stored user keys for {user_id}: {e}")
        return {}

    # Backfill the cache (best effort).
    if redis_client:
        try:
            redis_client.setex(f"user_keys:{user_id}", _CACHE_TTL_SECONDS, encrypted)
        except (RedisError, OSError, RuntimeError):  # nosec B110 - cache backfill is best-effort
            pass
    return keys


def save_user_keys(user_id: str, keys: dict[str, str]):
    """Persist encrypted user keys to the durable file store (and refresh cache)."""
    encrypted = encryption_service.encrypt_string(json.dumps(keys))

    # Durable write (source of truth).
    try:
        with _file_lock:
            store = _load_store()
            store[user_id] = encrypted
            _write_store(store)
    except OSError as e:
        logger.error(f"Failed to persist user keys for {user_id}: {e}")
        raise RuntimeError("Key storage unavailable") from e

    # Refresh the Redis cache (best effort).
    redis_client = get_redis()
    if redis_client:
        try:
            redis_client.setex(f"user_keys:{user_id}", _CACHE_TTL_SECONDS, encrypted)
        except (RedisError, OSError, RuntimeError):  # nosec B110 - cache refresh is best-effort
            pass


def delete_user_keys(user_id: str):
    """Delete all user keys from the durable store and the cache."""
    try:
        with _file_lock:
            store = _load_store()
            if user_id in store:
                del store[user_id]
                _write_store(store)
    except OSError as e:
        logger.warning(f"Failed to delete user keys for {user_id}: {e}")

    redis_client = get_redis()
    if redis_client:
        try:
            redis_client.delete(f"user_keys:{user_id}")
        except (RedisError, ConnectionError, OSError):  # nosec B110 - best-effort cache cleanup
            pass


def get_user_api_key(user_id: str, key_type: str) -> str | None:
    """Get a single API key for a user. Used by UserAPIKeys for server-side fallback."""
    keys = get_user_keys(user_id)
    return keys.get(key_type)
