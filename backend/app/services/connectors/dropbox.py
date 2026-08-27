from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.models.schemas import ConnectorType
from app.services import connector_credentials
from app.services.connectors.base import BaseConnector, FileInfo


class DropboxConnector(BaseConnector):
    """Dropbox connector using OAuth 2.0."""

    connector_type = ConnectorType.DROPBOX

    @property
    def is_configured(self) -> bool:
        return bool(
            connector_credentials.get("dropbox_app_key")
            and connector_credentials.get("dropbox_app_secret")
        )

    def get_auth_url(self, state: str) -> str:
        """Get Dropbox OAuth authorization URL."""
        params = {
            "client_id": connector_credentials.get("dropbox_app_key"),
            "redirect_uri": settings.dropbox_redirect_uri,
            "response_type": "code",
            "token_access_type": "offline",
            "state": state,
        }
        return f"https://www.dropbox.com/oauth2/authorize?{urlencode(params)}"

    async def handle_callback(self, code: str, state: str) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.dropboxapi.com/oauth2/token",
                data={
                    "client_id": connector_credentials.get("dropbox_app_key"),
                    "client_secret": connector_credentials.get("dropbox_app_secret"),
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.dropbox_redirect_uri,
                },
            )
            response.raise_for_status()
            tokens = response.json()

            self.credentials = {
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token"),
                "expires_at": datetime.now(UTC).timestamp() + tokens.get("expires_in", 14400),
                "account_id": tokens.get("account_id"),
            }
            self._save_credentials()

            return await self.get_account_info()

    async def refresh_token(self) -> bool:
        """Refresh the access token."""
        if not self.credentials.get("refresh_token"):
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.dropboxapi.com/oauth2/token",
                    data={
                        "client_id": connector_credentials.get("dropbox_app_key"),
                        "client_secret": connector_credentials.get("dropbox_app_secret"),
                        "refresh_token": self.credentials["refresh_token"],
                        "grant_type": "refresh_token",
                    },
                )
                response.raise_for_status()
                tokens = response.json()

                self.credentials["access_token"] = tokens["access_token"]
                self.credentials["expires_at"] = datetime.now(UTC).timestamp() + tokens.get(
                    "expires_in", 14400
                )
                self._save_credentials()
                return True
        except (httpx.HTTPStatusError, httpx.RequestError, KeyError, ValueError):
            return False

    async def _ensure_valid_token(self):
        """Ensure we have a valid access token."""
        if not self.credentials.get("access_token"):
            raise Exception("Not authenticated")

        expires_at = self.credentials.get("expires_at", 0)
        if datetime.now(UTC).timestamp() >= expires_at - 60:
            if not await self.refresh_token():
                raise Exception("Failed to refresh token")

    async def get_account_info(self) -> dict[str, Any]:
        """Get Dropbox account information."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.dropboxapi.com/2/users/get_current_account",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
            )
            response.raise_for_status()
            data = response.json()

            return {
                "name": data.get("name", {}).get("display_name"),
                "email": data.get("email"),
            }

    async def list_files(
        self, folder_id: str | None = None, page_token: str | None = None
    ) -> tuple[list[FileInfo], str | None]:
        """List files in Dropbox."""
        await self._ensure_valid_token()

        path = folder_id or ""
        headers = {"Authorization": f"Bearer {self.credentials['access_token']}"}

        async with httpx.AsyncClient() as client:
            if page_token:
                response = await client.post(
                    "https://api.dropboxapi.com/2/files/list_folder/continue",
                    headers=headers,
                    json={"cursor": page_token},
                )
            else:
                response = await client.post(
                    "https://api.dropboxapi.com/2/files/list_folder",
                    headers=headers,
                    json={"path": path, "recursive": False, "limit": 100},
                )
            response.raise_for_status()
            data = response.json()

            files = []
            for entry in data.get("entries", []):
                if entry[".tag"] == "folder":
                    mime_type = "folder"
                    size = 0
                else:
                    mime_type = self._get_mime_type(entry.get("name", ""))
                    size = entry.get("size", 0)

                modified = entry.get("server_modified") or entry.get("client_modified")
                modified_dt = (
                    datetime.fromisoformat(modified.replace("Z", "+00:00"))
                    if modified
                    else datetime.now(UTC)
                )

                files.append(
                    FileInfo(
                        id=entry.get("path_lower", entry.get("id", "")),
                        name=entry.get("name", ""),
                        mime_type=mime_type,
                        size=size,
                        modified_at=modified_dt,
                        path=entry.get("path_display"),
                        metadata={"tag": entry[".tag"]},
                    )
                )

            next_token = data.get("cursor") if data.get("has_more") else None
            return files, next_token

    def _get_mime_type(self, filename: str) -> str:
        """Infer MIME type from filename."""
        ext = filename.lower().split(".")[-1] if "." in filename else ""
        mime_map = {
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "txt": "text/plain",
            "rtf": "application/rtf",
            "xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        return mime_map.get(ext, "application/octet-stream")

    async def download_file(self, file_id: str) -> bytes:
        """Download a file from Dropbox."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://content.dropboxapi.com/2/files/download",
                headers={
                    "Authorization": f"Bearer {self.credentials['access_token']}",
                    "Dropbox-API-Arg": f'{{"path": "{file_id}"}}',
                },
            )
            response.raise_for_status()
            return response.content


dropbox_connector = DropboxConnector()
