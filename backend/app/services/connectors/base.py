import contextvars
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.config import settings
from app.models.schemas import ConnectorType
from app.services.encryption import encryption_service

logger = logging.getLogger(__name__)

# Context variable for current user_id (async-safe, request-scoped)
_connector_user_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_connector_user_ctx", default=None
)


@dataclass
class FileInfo:
    """Information about a file from a connector."""

    id: str
    name: str
    mime_type: str
    size: int
    modified_at: datetime
    path: str | None = None
    download_url: str | None = None
    metadata: dict[str, Any] = None


class BaseConnector(ABC):
    """Base class for all data source connectors.

    Credentials are isolated per-user via ``contextvars``.  Before calling any
    method that reads or writes credentials the caller must invoke
    ``BaseConnector.set_current_user(user_id)`` so the connector knows whose
    credentials to load/save.  The router layer handles this automatically.
    """

    connector_type: ConnectorType = None

    def __init__(self):
        # Per-user credential cache: {user_id: {cred dict}}
        # Kept in memory for the lifetime of the process to avoid repeated
        # disk reads within a single request.  Each entry is small (~1 KB).
        self._credentials_cache: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # User context helpers (async-safe via contextvars)
    # ------------------------------------------------------------------

    @staticmethod
    def set_current_user(user_id: str) -> None:
        """Set the current user for credential isolation (call from router)."""
        _connector_user_ctx.set(user_id)

    # ------------------------------------------------------------------
    # Credential path helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_user_id(user_id: str) -> str:
        """Sanitise user_id for safe use in file paths."""
        return re.sub(r"[^a-zA-Z0-9_-]", "_", user_id)

    def _get_credentials_path(self, user_id: str) -> str:
        """Get path to *user-scoped* credentials file."""
        safe_id = self._safe_user_id(user_id)
        return os.path.join(
            settings.upload_dir,
            f"credentials_{self.connector_type.value}_{safe_id}.json",
        )

    def _get_legacy_credentials_path(self) -> str:
        """Legacy (pre-isolation) global credentials file."""
        return os.path.join(
            settings.upload_dir,
            f"credentials_{self.connector_type.value}.json",
        )

    # ------------------------------------------------------------------
    # Low-level credential I/O (always user-scoped)
    # ------------------------------------------------------------------

    def _read_credentials_file(self, path: str) -> dict[str, Any]:
        """Read and decrypt a credentials file, returning {} on failure."""
        if not os.path.exists(path):
            return {}
        try:
            with open(path) as f:
                encrypted_data = f.read()
            if not encrypted_data:
                return {}
            try:
                decrypted = encryption_service.decrypt_string(encrypted_data)
                return json.loads(decrypted)
            except (ValueError, KeyError, ConnectionError, TimeoutError, OSError):
                # Legacy unencrypted file – migrate silently
                try:
                    creds = json.loads(encrypted_data)
                    # Re-save encrypted at the same path
                    self._write_credentials_file(path, creds)
                    logger.info("Migrated legacy unencrypted credentials to encrypted format")
                    return creds
                except (json.JSONDecodeError, ValueError):
                    return {}
        except OSError:
            return {}

    @staticmethod
    def _write_credentials_file(path: str, credentials: dict[str, Any]) -> None:
        """Encrypt and write credentials to *path* atomically with 0600 perms."""
        import os
        import stat

        try:
            json_data = json.dumps(credentials)
            encrypted_data = encryption_service.encrypt_string(json_data)
            tmp_path = f"{path}.tmp"
            with open(tmp_path, "w") as f:
                f.write(encrypted_data)
            try:
                os.chmod(
                    tmp_path, stat.S_IRUSR | stat.S_IWUSR
                )  # owner-only (best effort on Windows)
            except OSError:
                pass
            os.replace(tmp_path, path)  # atomic swap — no truncated file on crash
        except (ValueError, OSError, TypeError, RuntimeError) as e:
            logger.error(f"Error saving credentials: {e}")

    # ------------------------------------------------------------------
    # Public credential accessors (user-scoped via contextvars)
    # ------------------------------------------------------------------

    def _load_credentials_for_user(self, user_id: str) -> dict[str, Any]:
        """Load credentials for *user_id*, migrating legacy file if needed."""
        # 1. Try user-scoped file
        path = self._get_credentials_path(user_id)
        creds = self._read_credentials_file(path)
        if creds:
            return creds

        # 2. One-time migration from legacy global file
        legacy_path = self._get_legacy_credentials_path()
        if os.path.exists(legacy_path):
            creds = self._read_credentials_file(legacy_path)
            if creds:
                # Persist under the user-scoped path
                self._write_credentials_file(path, creds)
                # Remove the global file so it can't be claimed by another user
                try:
                    os.remove(legacy_path)
                except OSError:
                    pass
                logger.info(
                    f"Migrated global credentials for {self.connector_type.value} "
                    f"to user-scoped file for user {self._safe_user_id(user_id)}"
                )
                return creds

        return {}

    def _save_credentials_for_user(self, user_id: str, creds: dict[str, Any]) -> None:
        path = self._get_credentials_path(user_id)
        self._write_credentials_file(path, creds)

    def _clear_credentials_for_user(self, user_id: str) -> None:
        self._credentials_cache.pop(user_id, None)
        path = self._get_credentials_path(user_id)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # self.credentials property – drop-in replacement for subclasses
    # ------------------------------------------------------------------

    @property
    def credentials(self) -> dict[str, Any]:
        """Return credentials for the *current* user (set via set_current_user)."""
        user_id = _connector_user_ctx.get()
        if not user_id:
            return {}
        if user_id not in self._credentials_cache:
            self._credentials_cache[user_id] = self._load_credentials_for_user(user_id)
        return self._credentials_cache[user_id]

    @credentials.setter
    def credentials(self, value: dict[str, Any]) -> None:
        user_id = _connector_user_ctx.get()
        if user_id:
            self._credentials_cache[user_id] = value

    # Legacy helpers – now user-scoped via the property
    def _save_credentials(self) -> None:
        """Persist credentials for the current user to disk."""
        user_id = _connector_user_ctx.get()
        if not user_id:
            logger.warning("Cannot save credentials: no user context set")
            return
        creds = self._credentials_cache.get(user_id, {})
        self._save_credentials_for_user(user_id, creds)

    def _clear_credentials(self) -> None:
        """Clear credentials for the current user."""
        user_id = _connector_user_ctx.get()
        if not user_id:
            return
        self._clear_credentials_for_user(user_id)

    @property
    def is_connected(self) -> bool:
        """Check if connector has valid credentials for the current user."""
        return bool(self.credentials.get("access_token"))

    @property
    def is_configured(self) -> bool:
        """Check if connector has required OAuth/API credentials configured.
        Subclasses should override to check their specific required settings."""
        return True

    @abstractmethod
    def get_auth_url(self, state: str) -> str:
        """Get OAuth authorization URL."""
        pass

    @abstractmethod
    async def handle_callback(self, code: str, state: str) -> dict[str, Any]:
        """Handle OAuth callback and exchange code for tokens."""
        pass

    @abstractmethod
    async def refresh_token(self) -> bool:
        """Refresh access token if expired."""
        pass

    @abstractmethod
    async def get_account_info(self) -> dict[str, Any]:
        """Get connected account information."""
        pass

    @abstractmethod
    async def list_files(
        self, folder_id: str | None = None, page_token: str | None = None
    ) -> tuple[list[FileInfo], str | None]:
        """List files in a folder. Returns (files, next_page_token)."""
        pass

    @abstractmethod
    async def download_file(self, file_id: str) -> bytes:
        """Download a file's content."""
        pass

    async def crawl_all_files(
        self, supported_types: list[str] = None
    ) -> AsyncGenerator[FileInfo, None]:
        """Crawl all files recursively."""
        if supported_types is None:
            supported_types = [
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/msword",
                "text/plain",
            ]

        async for file_info in self._crawl_folder(None, supported_types):
            yield file_info

    async def _crawl_folder(
        self, folder_id: str | None, supported_types: list[str]
    ) -> AsyncGenerator[FileInfo, None]:
        """Recursively crawl a folder."""
        page_token = None

        while True:
            files, next_token = await self.list_files(folder_id, page_token)

            for file_info in files:
                # Check if it's a supported file type
                if file_info.mime_type in supported_types:
                    yield file_info
                # If it's a folder, recurse into it
                elif file_info.mime_type in [
                    "application/vnd.google-apps.folder",
                    "folder",
                ]:
                    async for sub_file in self._crawl_folder(file_info.id, supported_types):
                        yield sub_file

            if not next_token:
                break
            page_token = next_token

    async def disconnect(self):
        """Disconnect and clear credentials."""
        self._clear_credentials()

    async def get_status(self) -> dict[str, Any]:
        """Get connector status."""
        configured = self.is_configured
        if not configured:
            return {"connected": False, "configured": False, "type": self.connector_type.value}

        if not self.is_connected:
            return {"connected": False, "configured": True, "type": self.connector_type.value}

        try:
            account = await self.get_account_info()
            return {
                "connected": True,
                "configured": True,
                "type": self.connector_type.value,
                "account_name": account.get("name"),
                "account_email": account.get("email"),
                "last_sync": self.credentials.get("last_sync"),
            }
        except (httpx.HTTPError, ConnectionError, TimeoutError):
            return {
                "connected": False,
                "configured": True,
                "type": self.connector_type.value,
                "error": "Failed to get account info",
            }


# ----------------------------------------------------------------------
# Right-to-erasure helpers (module-level; used by user deletion)
# ----------------------------------------------------------------------


def _credentials_path_for(connector_type: ConnectorType, user_id: str) -> str:
    """Path of the user-scoped credential file for *connector_type*."""
    safe_id = BaseConnector._safe_user_id(user_id)
    return os.path.join(settings.upload_dir, f"credentials_{connector_type.value}_{safe_id}.json")


def _read_credentials_at(path: str) -> dict[str, Any]:
    """Decrypt a credential file for revocation; {} on any failure. Never writes."""
    try:
        with open(path) as f:
            raw = f.read()
        if not raw:
            return {}
        try:
            return json.loads(encryption_service.decrypt_string(raw))
        except (ValueError, KeyError, TypeError, OSError):
            return json.loads(raw)  # legacy unencrypted file
    except (OSError, ValueError, TypeError):
        return {}


async def _revoke_token_best_effort(connector_type: ConnectorType, creds: dict[str, Any]) -> bool:
    """Invalidate the provider-side OAuth grant where a cheap endpoint exists.

    Google: POST oauth2.googleapis.com/revoke with the refresh token (falls back
    to the access token); revoking either invalidates the whole grant.
    Dropbox: POST /2/auth/token/revoke with the bearer access token, which also
    disables the paired refresh token. Other providers have no comparably cheap
    endpoint, so their files are just deleted. Failures are logged, not raised.
    """
    try:
        if connector_type in (ConnectorType.GOOGLE_DRIVE, ConnectorType.GOOGLE_PICKER):
            token = creds.get("refresh_token") or creds.get("access_token")
            if not token:
                return False
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://oauth2.googleapis.com/revoke", data={"token": token}
                )
        elif connector_type == ConnectorType.DROPBOX:
            token = creds.get("access_token")
            if not token:
                return False
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.dropboxapi.com/2/auth/token/revoke",
                    headers={"Authorization": f"Bearer {token}"},
                )
        else:
            return False
        if resp.is_success:
            return True
        logger.warning(
            "Token revocation for %s returned HTTP %s", connector_type.value, resp.status_code
        )
        return False
    except (httpx.HTTPError, OSError, ValueError) as e:
        logger.warning("Token revocation for %s failed: %s", connector_type.value, e)
        return False


async def delete_user_credentials(user_id: str) -> dict[str, int]:
    """Erase every connector credential file for *user_id* (right-to-erasure).

    Iterates every ``ConnectorType``; for providers with a cheap revocation
    endpoint the stored token is revoked best-effort first, then the file is
    deleted and the in-process credential cache is dropped. Returns
    ``{"connector_credentials_deleted": n, "connector_tokens_revoked": m}``.
    """
    deleted = 0
    revoked = 0
    for connector_type in ConnectorType:
        path = _credentials_path_for(connector_type, user_id)
        if not os.path.exists(path):
            continue
        creds = _read_credentials_at(path)
        if creds and await _revoke_token_best_effort(connector_type, creds):
            revoked += 1
        try:
            os.remove(path)
            deleted += 1
        except OSError as e:
            logger.warning("Could not delete %s credentials for user: %s", connector_type.value, e)

    # Drop the per-process cache so a live connector object cannot resurrect
    # the tokens for the rest of this process's lifetime.
    try:
        from app.services.connectors import CONNECTORS

        for connector in CONNECTORS.values():
            connector._credentials_cache.pop(user_id, None)
    except ImportError:  # pragma: no cover - registry not importable in isolation
        pass

    return {"connector_credentials_deleted": deleted, "connector_tokens_revoked": revoked}
