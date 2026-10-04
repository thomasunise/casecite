"""
OAuth state management for connectors.

Extracted from routers/connectors.py to keep business logic in services.
Uses Redis with in-memory fallback. Sync progress is tracked by the job
manager (services/job_queue.py), not here.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from app.models.schemas import ConnectorType
from app.redis_utils import RedisError, get_redis

logger = logging.getLogger(__name__)

# In-memory fallback (used when Redis is unavailable)
_oauth_states_memory: dict = {}


def store_oauth_state(
    state: str, user_id: str, connector_type: ConnectorType, ttl_seconds: int = 600
):
    """Store OAuth state with user binding and expiry (10 min default)."""
    data = {
        "user_id": user_id,
        "connector_type": connector_type.value,
        "expires_at": (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat(),
        "created_at": datetime.now(UTC).isoformat(),
    }

    redis_client = get_redis()
    if redis_client:
        try:
            redis_client.setex(f"oauth_state:{state}", ttl_seconds, json.dumps(data))
            return
        except (RedisError, ConnectionError, OSError):
            pass

    # In-memory fallback. Drop abandoned (expired, never-redeemed) states first
    # so the dict cannot grow without bound.
    now = datetime.now(UTC)
    for stale in [k for k, v in _oauth_states_memory.items() if v["expires_at"] < now]:
        del _oauth_states_memory[stale]
    _oauth_states_memory[state] = {
        **data,
        "expires_at": datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    }


def validate_oauth_state(state: str, connector_type: ConnectorType) -> str | None:
    """Validate OAuth state and return user_id if valid. Deletes state after use (single-use)."""
    redis_client = get_redis()
    if redis_client:
        try:
            data_str = redis_client.get(f"oauth_state:{state}")
            if not data_str:
                return None

            data = json.loads(data_str)
            expires_at = datetime.fromisoformat(data["expires_at"])

            if expires_at < datetime.now(UTC):
                redis_client.delete(f"oauth_state:{state}")
                return None

            if data["connector_type"] != connector_type.value:
                logger.warning(
                    f"OAuth state connector type mismatch: expected {connector_type.value}, got {data['connector_type']}"
                )
                return None

            redis_client.delete(f"oauth_state:{state}")
            return data["user_id"]
        except (ValueError, KeyError, ConnectionError, TimeoutError, OSError) as e:
            logger.warning(f"Redis OAuth state validation failed: {e}")

    # In-memory fallback
    state_data = _oauth_states_memory.get(state)
    if not state_data:
        return None

    if state_data["expires_at"] < datetime.now(UTC):
        del _oauth_states_memory[state]
        return None

    if state_data["connector_type"] != connector_type.value:
        logger.warning(
            f"OAuth state connector type mismatch: expected {connector_type.value}, got {state_data['connector_type']}"
        )
        return None

    user_id = state_data["user_id"]
    del _oauth_states_memory[state]
    return user_id
