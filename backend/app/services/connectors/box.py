from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.models.schemas import ConnectorType
from app.services import connector_credentials
from app.services.connectors.base import BaseConnector, FileInfo


class BoxConnector(BaseConnector):
    """Box connector using OAuth 2.0."""

    connector_type = ConnectorType.BOX

    @property
    def is_configured(self) -> bool:
        return bool(
            connector_credentials.get("box_client_id")
            and connector_credentials.get("box_client_secret")
        )

    def get_auth_url(self, state: str) -> str:
        """Get Box OAuth authorization URL."""
        params = {
            "client_id": connector_credentials.get("box_client_id"),
            "redirect_uri": settings.box_redirect_uri,
            "response_type": "code",
            "state": state,
        }
        return f"https://account.box.com/api/oauth2/authorize?{urlencode(params)}"

    async def handle_callback(self, code: str, state: str) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.box.com/oauth2/token",
                data={
                    "client_id": connector_credentials.get("box_client_id"),
                    "client_secret": connector_credentials.get("box_client_secret"),
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            tokens = response.json()

            self.credentials = {
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token"),
                "expires_at": datetime.now(UTC).timestamp() + tokens.get("expires_in", 3600),
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
                    "https://api.box.com/oauth2/token",
                    data={
                        "client_id": connector_credentials.get("box_client_id"),
                        "client_secret": connector_credentials.get("box_client_secret"),
                        "refresh_token": self.credentials["refresh_token"],
                        "grant_type": "refresh_token",
                    },
                )
                response.raise_for_status()
                tokens = response.json()

                self.credentials["access_token"] = tokens["access_token"]
                if tokens.get("refresh_token"):
                    self.credentials["refresh_token"] = tokens["refresh_token"]
                self.credentials["expires_at"] = datetime.now(UTC).timestamp() + tokens.get(
                    "expires_in", 3600
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
        """Get Box account information."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.box.com/2.0/users/me",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
            )
            response.raise_for_status()
            data = response.json()

            return {"name": data.get("name"), "email": data.get("login")}

    async def list_files(
        self, folder_id: str | None = None, page_token: str | None = None
    ) -> tuple[list[FileInfo], str | None]:
        """List files in Box."""
        await self._ensure_valid_token()

        folder_id = folder_id or "0"  # 0 is root folder
        offset = int(page_token) if page_token else 0

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.box.com/2.0/folders/{folder_id}/items",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
                params={"fields": "id,name,type,size,modified_at", "limit": 100, "offset": offset},
            )
            response.raise_for_status()
            data = response.json()

            files = []
            for item in data.get("entries", []):
                if item["type"] == "folder":
                    mime_type = "folder"
                else:
                    # Box doesn't provide mime type directly, infer from extension
                    mime_type = self._get_mime_type(item["name"])

                files.append(
                    FileInfo(
                        id=item["id"],
                        name=item["name"],
                        mime_type=mime_type,
                        size=item.get("size", 0),
                        modified_at=datetime.fromisoformat(
                            item["modified_at"].replace("Z", "+00:00")
                        )
                        if item.get("modified_at")
                        else datetime.now(UTC),
                        metadata={"type": item["type"]},
                    )
                )

            # Calculate next offset
            total = data.get("total_count", 0)
            next_offset = offset + len(data.get("entries", []))
            next_token = str(next_offset) if next_offset < total else None

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
        """Download a file from Box."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                f"https://api.box.com/2.0/files/{file_id}/content",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
            )
            response.raise_for_status()
            return response.content

    async def get_downscoped_token(
        self, scopes: str = "base_picker item_download root_readonly"
    ) -> dict[str, Any]:
        """Exchange the stored token for a downscoped one for Box UI Elements.

        The picker runs in the browser; handing it the full connector token
        would leak read-write account access, so it gets a token limited to
        picking and downloading.
        """
        await self._ensure_valid_token()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.box.com/oauth2/token",
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                    "subject_token": self.credentials["access_token"],
                    "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                    "scope": scopes,
                },
            )
            response.raise_for_status()
            data = response.json()
            return {
                "access_token": data["access_token"],
                "expires_in": data.get("expires_in", 3600),
            }


box_connector = BoxConnector()
