import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings
from app.models.schemas import ConnectorType
from app.services.connectors.base import BaseConnector, ConnectorError, FileInfo

# Filevine sessions are short-lived; re-handshake well before the documented
# lifetime so long crawls never ride an expired session.
_SESSION_TTL_SECONDS = 10 * 60


def _native(value: Any) -> str:
    """Filevine ids arrive as {"native": ..., "partner": ...} or as scalars."""
    if isinstance(value, dict):
        return str(value.get("native", ""))
    return str(value) if value is not None else ""


class FilevineConnector(BaseConnector):
    """Filevine connector using the API key + session handshake.

    Filevine does not use OAuth. Auth is a signed session request:
    POST /session with the API key, an ISO-8601 UTC timestamp, and
    md5(key/timestamp/secret). The session's access token, user id, and
    org id are then sent on every API call.

    Access model: the API key is one firm-wide credential, so a session sees
    every project the key can see — Filevine's per-user project permissions
    do not apply. Two controls keep that from reaching ordinary users:

    * the connector stays off until an administrator sets
      ``FILEVINE_ENABLED=true`` alongside the key and secret, and
    * ``requires_admin`` makes the router refuse connect/sync/disconnect to
      anyone without the ``admin.settings`` permission, and report the
      connector as not connected to everyone else.

    Per-user Filevine credentials would lift the restriction, but the
    key + secret handshake has no per-user equivalent here.
    """

    connector_type = ConnectorType.FILEVINE
    requires_admin = True

    @property
    def is_configured(self) -> bool:
        return bool(
            settings.filevine_enabled and settings.filevine_api_key and settings.filevine_api_secret
        )

    def __init__(self):
        super().__init__()
        self.base_url = settings.filevine_base_url

    @property
    def is_connected(self) -> bool:
        """Configured and explicitly enabled; the router adds the admin gate."""
        return self.is_configured

    def get_auth_url(self, state: str) -> str:
        """Filevine uses API keys, not OAuth. Return config URL."""
        return f"/settings/integrations/filevine?state={state}"

    async def handle_callback(self, code: str, state: str) -> dict[str, Any]:
        """No OAuth callback — establish a session to validate configuration."""
        await self._create_session()
        return await self.get_account_info()

    async def refresh_token(self) -> bool:
        """Re-establish the session (Filevine sessions are short-lived)."""
        try:
            await self._create_session()
            return True
        except (httpx.HTTPError, KeyError, ValueError):
            return False

    async def _create_session(self) -> None:
        """Perform the signed session handshake and cache the session."""
        if not self.is_configured:
            raise ConnectorError("Filevine is not enabled or its API key/secret are missing")

        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw = f"{settings.filevine_api_key}/{timestamp}/{settings.filevine_api_secret}"
        api_hash = hashlib.md5(raw.encode()).hexdigest()  # noqa: S324  # nosec B324 - Filevine's documented scheme

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/session",
                json={
                    "mode": "key",
                    "apiKey": settings.filevine_api_key,
                    "apiHash": api_hash,
                    "apiTimestamp": timestamp,
                },
            )
            response.raise_for_status()
            data = response.json()

        access_token = data.get("accessToken") or data.get("authToken") or ""
        if not access_token:
            raise ConnectorError("Filevine session response contained no access token")

        creds = dict(self.credentials)
        creds.update(
            {
                "access_token": access_token,
                "refresh_token": data.get("refreshToken", ""),
                "user_id": _native(data.get("userId")),
                "org_id": _native(data.get("orgId")),
                "session_expires_at": datetime.now(UTC).timestamp() + _SESSION_TTL_SECONDS,
            }
        )
        self.credentials = creds
        self._save_credentials()

    async def _ensure_session(self) -> None:
        expires_at = self.credentials.get("session_expires_at", 0)
        if (
            not self.credentials.get("access_token")
            or datetime.now(UTC).timestamp() >= expires_at - 60
        ):
            await self._create_session()

    def _get_headers(self) -> dict[str, str]:
        """Session headers for Filevine API calls."""
        headers = {
            "Authorization": f"Bearer {self.credentials.get('access_token', '')}",
            "Content-Type": "application/json",
        }
        if self.credentials.get("user_id"):
            headers["x-fv-userid"] = self.credentials["user_id"]
        if self.credentials.get("org_id"):
            headers["x-fv-orgid"] = self.credentials["org_id"]
        return headers

    async def get_account_info(self) -> dict[str, Any]:
        """Get Filevine account information."""
        await self._ensure_session()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/core/users/me", headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()

            return {
                "name": f"{data.get('firstName', '')} {data.get('lastName', '')}".strip(),
                "email": data.get("email", ""),
                "org_id": self.credentials.get("org_id", ""),
            }

    async def list_projects(self, page: int = 1) -> dict[str, Any]:
        """List Filevine projects (cases/matters)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/core/projects",
                headers=self._get_headers(),
                params={"requestedPage": page, "pageSize": 50},
            )
            response.raise_for_status()
            return response.json()

    async def list_files(
        self, folder_id: str | None = None, page_token: str | None = None
    ) -> tuple[list[FileInfo], str | None]:
        """List files in Filevine.

        The root listing emits every project as a folder entry, so the crawl
        recurses into each matter's documents with full pagination instead of
        sampling a capped slice.
        """
        await self._ensure_session()

        page = int(page_token) if page_token else 1

        # folder_id is treated as project_id in Filevine
        if folder_id:
            return await self._list_project_documents(folder_id, page)
        return await self._list_projects_as_folders(page)

    async def _list_projects_as_folders(self, page: int) -> tuple[list[FileInfo], str | None]:
        """Emit projects as folders so the base crawl covers every matter."""
        projects_data = await self.list_projects(page)
        projects = projects_data.get("items", [])

        folders = []
        for project in projects:
            project_id = _native(project.get("projectId"))
            if not project_id:
                continue
            folders.append(
                FileInfo(
                    id=project_id,
                    name=project.get("projectName", "") or f"Project {project_id}",
                    mime_type="folder",
                    size=0,
                    modified_at=datetime.now(UTC),
                    metadata={"kind": "project"},
                )
            )

        has_more = projects_data.get("hasMore", False)
        next_token = str(page + 1) if has_more else None
        return folders, next_token

    async def _list_project_documents(
        self, project_id: str, page: int
    ) -> tuple[list[FileInfo], str | None]:
        """List documents in a specific project."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/core/projects/{quote(project_id, safe='')}/docs",
                headers=self._get_headers(),
                params={"requestedPage": page, "pageSize": 50},
            )
            response.raise_for_status()
            data = response.json()

            files = []
            for doc in data.get("items", []):
                try:
                    files.append(self._parse_document(doc, {"projectId": {"native": project_id}}))
                except (KeyError, TypeError, json.JSONDecodeError):  # nosec B112 - skip malformed docs
                    continue

            has_more = data.get("hasMore", False)
            next_token = str(page + 1) if has_more else None

            return files, next_token

    def _parse_document(self, doc: dict[str, Any], project: dict[str, Any]) -> FileInfo:
        """Parse Filevine document into FileInfo."""
        doc_id = _native(doc.get("docId"))
        filename = doc.get("filename", "")
        extension = doc.get("extension", "")

        if extension and not filename.endswith(f".{extension}"):
            filename = f"{filename}.{extension}"

        modified = doc.get("lastUpdated", "")
        modified_at = datetime.now(UTC)
        if modified:
            try:
                modified_at = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            except ValueError:  # nosec B110 - Use default datetime on parse failure
                pass

        return FileInfo(
            id=doc_id,
            name=filename,
            mime_type=self._get_mime_type(extension),
            size=doc.get("size", 0),
            modified_at=modified_at,
            metadata={
                "project_id": _native(project.get("projectId")),
                "project_name": project.get("projectName", ""),
                "doc_type": doc.get("docType"),
                "uploaded_by": doc.get("uploadedBy"),
            },
        )

    def _get_mime_type(self, extension: str) -> str:
        """Get MIME type from extension."""
        if not extension:
            return "application/octet-stream"

        ext = extension.lower().lstrip(".")
        mime_map = {
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "txt": "text/plain",
            "rtf": "application/rtf",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
        }
        return mime_map.get(ext, "application/octet-stream")

    async def download_file(self, file_id: str) -> bytes:
        """Download a file from Filevine."""
        await self._ensure_session()

        async with httpx.AsyncClient(follow_redirects=True) as client:
            return await self._download_capped(
                client,
                "GET",
                f"{self.base_url}/core/docs/{quote(file_id, safe='')}/download",
                headers=self._get_headers(),
            )


filevine_connector = FilevineConnector()
