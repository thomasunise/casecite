from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.models.schemas import ConnectorType
from app.services import connector_credentials
from app.services.connectors.base import BaseConnector, FileInfo


class GoogleDriveConnector(BaseConnector):
    """Google Drive connector using OAuth 2.0."""

    connector_type = ConnectorType.GOOGLE_DRIVE

    @property
    def is_configured(self) -> bool:
        return bool(
            connector_credentials.get("google_client_id")
            and connector_credentials.get("google_client_secret")
        )

    SCOPES = [
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    def get_auth_url(self, state: str) -> str:
        """Get Google OAuth authorization URL."""
        params = {
            "client_id": connector_credentials.get("google_client_id"),
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    async def handle_callback(self, code: str, state: str) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": connector_credentials.get("google_client_id"),
                    "client_secret": connector_credentials.get("google_client_secret"),
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.google_redirect_uri,
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
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": connector_credentials.get("google_client_id"),
                        "client_secret": connector_credentials.get("google_client_secret"),
                        "refresh_token": self.credentials["refresh_token"],
                        "grant_type": "refresh_token",
                    },
                )
                response.raise_for_status()
                tokens = response.json()

                self.credentials["access_token"] = tokens["access_token"]
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

        # Check if token is expired
        expires_at = self.credentials.get("expires_at", 0)
        if datetime.now(UTC).timestamp() >= expires_at - 60:  # 60 second buffer
            if not await self.refresh_token():
                raise Exception("Failed to refresh token")

    async def get_account_info(self) -> dict[str, Any]:
        """Get Google account information."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
            )
            response.raise_for_status()
            data = response.json()

            return {
                "name": data.get("name"),
                "email": data.get("email"),
                "picture": data.get("picture"),
            }

    async def list_files(
        self, folder_id: str | None = None, page_token: str | None = None
    ) -> tuple[list[FileInfo], str | None]:
        """List files in Google Drive."""
        await self._ensure_valid_token()

        # Build query
        query_parts = ["trashed = false"]
        if folder_id:
            query_parts.append(f"'{folder_id}' in parents")
        else:
            query_parts.append("'root' in parents")

        params = {
            "q": " and ".join(query_parts),
            "fields": "nextPageToken, files(id, name, mimeType, size, modifiedTime, parents)",
            "pageSize": 100,
        }
        if page_token:
            params["pageToken"] = page_token

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            files = []
            for item in data.get("files", []):
                files.append(
                    FileInfo(
                        id=item["id"],
                        name=item["name"],
                        mime_type=item["mimeType"],
                        size=int(item.get("size", 0)),
                        modified_at=datetime.fromisoformat(
                            item["modifiedTime"].replace("Z", "+00:00")
                        ),
                        metadata={"parents": item.get("parents", [])},
                    )
                )

            return files, data.get("nextPageToken")

    async def download_file(self, file_id: str) -> bytes:
        """Download a file from Google Drive."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient() as client:
            # First, check if it's a Google Doc that needs export
            response = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
                params={"fields": "mimeType"},
            )
            response.raise_for_status()
            mime_type = response.json().get("mimeType", "")

            # Google Docs need to be exported
            export_map = {
                "application/vnd.google-apps.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.google-apps.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            }

            if mime_type in export_map:
                response = await client.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                    headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
                    params={"mimeType": export_map[mime_type]},
                )
            else:
                response = await client.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}",
                    headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
                    params={"alt": "media"},
                )

            response.raise_for_status()
            return response.content


google_drive_connector = GoogleDriveConnector()
