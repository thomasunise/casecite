"""
Shared Redis singleton utility.

Provides a lazy-initialized Redis client and a safe RedisError class
so that every module doesn't need its own try/import/fallback boilerplate.
"""

import logging

from app.config import settings

try:
    from redis.exceptions import RedisError
except ImportError:

    class RedisError(Exception):  # type: ignore[no-redef]
        pass


logger = logging.getLogger(__name__)

# Sentinel values: None = not yet attempted, False = attempted and failed
_redis_client = None


def _is_production() -> bool:
    """Return True when running in production (DEBUG=false)."""
    return not settings.debug


def get_redis():
    """Return a shared Redis client, or None if unavailable.

    Connects lazily on the first call.  If the connection fails the failure
    is cached (``False`` sentinel) so subsequent calls return ``None``
    immediately without retrying.
    """
    global _redis_client

    if _redis_client is False:
        return None

    if _redis_client is not None:
        return _redis_client

    if not settings.redis_url:
        _redis_client = False
        return None

    try:
        import redis

        client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=settings.redis_socket_timeout,
        )
        client.ping()
        logger.info("Redis connected (shared singleton)")
        _redis_client = client
        return _redis_client
    except Exception as e:  # redis.exceptions.* don't subclass the builtins
        # redis.exceptions.ConnectionError/TimeoutError derive from RedisError,
        # not from the builtin ConnectionError/TimeoutError, so an explicit
        # tuple of builtins let a refused connection escape as an unhandled
        # exception at import time (AuthService() pings Redis when constructed).
        logger.warning(f"Redis unavailable ({e}), features will use in-memory fallback")
        _redis_client = False
        return None


def require_redis():
    """Return a Redis client, retrying once if the cached sentinel says unavailable.

    Security-critical call sites use this instead of ``get_redis()`` so that
    in production a transient Redis blip doesn't permanently disable Redis
    for the process lifetime.  If Redis is still unreachable after the retry
    the caller receives ``None`` and must decide how to fail (typically
    fail-closed in production, in-memory fallback in dev/demo).
    """
    global _redis_client

    client = get_redis()
    if client is not None:
        return client

    # In production, reset the failure sentinel and retry once — Redis may
    # have recovered from a brief network hiccup.
    if _is_production() and _redis_client is False:
        logger.warning("Redis unavailable in production — retrying once")
        _redis_client = None  # reset sentinel so get_redis() re-attempts
        client = get_redis()
        if client is not None:
            return client
        logger.critical(
            "Redis unavailable in production after retry — "
            "security-critical operations will fail closed"
        )

    return None
