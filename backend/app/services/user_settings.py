"""
User Settings Service

Provides per-user RAG settings persistence (load/save from JSON files).
"""

import json
import logging
import os

from app.config import settings
from app.models.schemas import RAGSettings

logger = logging.getLogger(__name__)

# Per-user settings directory
SETTINGS_DIR = os.path.join(settings.chroma_persist_dir, "..", "user_settings")
try:
    os.makedirs(SETTINGS_DIR, exist_ok=True)
except PermissionError as e:
    # Never fall back to the system temp dir: settings hold a firm's playbook
    # and practice profile, and a temp dir is neither persistent nor private.
    raise RuntimeError(
        f"Cannot create the user settings directory {os.path.abspath(SETTINGS_DIR)}: {e}. "
        "The data volume must be writable by the application user."
    ) from e


def _get_user_settings_path(user_id: str) -> str:
    """Get the settings file path for a specific user."""
    # Sanitize user_id to prevent path traversal
    safe_id = "".join(c for c in user_id if c.isalnum() or c in "-_")
    return os.path.join(SETTINGS_DIR, f"rag_settings_{safe_id}.json")


def load_user_settings(user_id: str) -> RAGSettings:
    """Load settings for a specific user, falling back to defaults."""
    settings_path = _get_user_settings_path(user_id)
    try:
        if os.path.exists(settings_path):
            with open(settings_path) as f:
                data = json.load(f)
                return RAGSettings(**data)
    except (ValueError, KeyError, OSError) as e:
        logger.warning(f"Could not load settings for user {user_id}: {e}")
    return RAGSettings()


def save_user_settings(user_id: str, rag_settings: RAGSettings) -> None:
    """Save settings for a specific user."""
    settings_path = _get_user_settings_path(user_id)
    try:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, "w") as f:
            json.dump(rag_settings.model_dump(), f, indent=2)
    except (ValueError, KeyError, OSError) as e:
        logger.warning(f"Could not save settings for user {user_id}: {e}")


def delete_user_settings(user_id: str) -> int:
    """Erase the per-user settings file (right-to-erasure).

    Returns the number of files removed (0 or 1). Missing files are not an
    error; unexpected OS errors are logged and counted as not deleted.
    """
    settings_path = _get_user_settings_path(user_id)
    if not os.path.exists(settings_path):
        return 0
    try:
        os.remove(settings_path)
        return 1
    except OSError as e:
        logger.warning(f"Could not delete settings for user {user_id}: {e}")
        return 0
