from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from app.config import settings
from app.models.schemas import ConnectorType
from app.services.connectors.base import BaseConnector, ConnectorError, FileInfo


class IManageConnector(BaseConnector):
    """iManage Work connector using OAuth 2.0.

    NOT VALIDATED AGAINST A LIVE TENANT. The endpoint paths used here
    (customer discovery, the document listing and the download route) were
    written from iManage's published API shape and are exercised only by
    mocked unit tests; no real iManage Work environment has been used to
    confirm them. Treat this connector as experimental until it has been run
    against your tenant, and expect to adjust paths for your Work version.
    """

    connector_type = ConnectorType.IMANAGE

    @property
    def is_configured(self) -> bool:
        return bool(settings.imanage_client_id and settings.imanage_client_secret)

    def __init__(self):
        super().__init__()
        self.base_url = settings.imanage_base_url or "https://cloudimanage.com"

    def get_auth_url(self, state: str) -> str:
        """Get iManage OAuth authorization URL."""
        params = {
            "client_id": settings.imanage_client_id,
            "redirect_uri": settings.imanage_redirect_uri,
            "response_type": "code",
            "scope": "user",
            "state": state,
        }
        return f"{self.base_url}/auth/oauth2/authorize?{urlencode(params)}"

    async def handle_callback(self, code: str, state: str) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/auth/oauth2/token",
                data={
                    "client_id": settings.imanage_client_id,
                    "client_secret": settings.imanage_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.imanage_redirect_uri,
                },
            )
            response.raise_for_status()
            tokens = response.json()

            self.credentials = {
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token"),
                "expires_at": datetime.now(UTC).timestamp() + tokens.get("expires_in", 3600),
                "customer_id": tokens.get("customer_id"),
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
                    f"{self.base_url}/auth/oauth2/token",
                    data={
                        "client_id": settings.imanage_client_id,
                        "client_secret": settings.imanage_client_secret,
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
        """Ensure we have a valid access token and a resolved customer_id."""
        if not self.credentials.get("access_token"):
            raise ConnectorError("Not authenticated")

        expires_at = self.credentials.get("expires_at", 0)
        if datetime.now(UTC).timestamp() >= expires_at - 60:
            if not await self.refresh_token():
                raise ConnectorError("Failed to refresh token")

        # The token response does not reliably include customer_id; without it
        # every Work API URL is malformed, so discover it once and persist.
        if not self.credentials.get("customer_id"):
            await self._discover_customer_id()

    async def _discover_customer_id(self) -> None:
        """Resolve customer_id via the Work API customers endpoint."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/work/api/v2/customers",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
            )
            response.raise_for_status()
            customers = response.json().get("data", [])
            if not customers:
                raise ConnectorError("iManage returned no customers for this account")
            self.credentials["customer_id"] = str(customers[0].get("id", ""))
            self._save_credentials()

    def _get_api_url(self) -> str:
        """Get the API base URL."""
        customer_id = self.credentials.get("customer_id", "")
        return f"{self.base_url}/work/api/v2/customers/{customer_id}"

    async def get_account_info(self) -> dict[str, Any]:
        """Get iManage account information."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._get_api_url()}/users/me",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
            )
            response.raise_for_status()
            data = response.json().get("data", {})

            return {
                "name": data.get("name", ""),
                "email": data.get("email", ""),
                "user_id": data.get("id", ""),
            }

    async def list_files(
        self, folder_id: str | None = None, page_token: str | None = None
    ) -> tuple[list[FileInfo], str | None]:
        """List files in iManage."""
        await self._ensure_valid_token()

        # Default to searching across all libraries if no folder specified
        offset = int(page_token) if page_token else 0

        params = {"offset": offset, "limit": 100}

        async with httpx.AsyncClient() as client:
            if folder_id:
                url = f"{self._get_api_url()}/folders/{quote(folder_id, safe='')}/documents"
            else:
                # Search for recent documents
                url = f"{self._get_api_url()}/documents"
                params["sort"] = "edit_date:desc"

            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            files = []
            for item in data.get("data", []):
                # Determine mime type from extension
                extension = item.get("extension", "").lower()
                mime_type = self._get_mime_type(extension)

                edit_date = item.get("edit_date", "")
                modified_at = datetime.now(UTC)
                if edit_date:
                    try:
                        modified_at = datetime.fromisoformat(edit_date.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                name = item.get("name", "")
                if extension and not name.lower().endswith(f".{extension}"):
                    name = f"{name}.{extension}"

                files.append(
                    FileInfo(
                        id=item.get("id", ""),
                        name=name,
                        mime_type=mime_type,
                        size=item.get("size", 0),
                        modified_at=modified_at,
                        metadata={
                            "library": item.get("database"),
                            "version": item.get("version"),
                            "class": item.get("class"),
                            "author": item.get("author"),
                        },
                    )
                )

            # Pagination
            total = data.get("total_count", 0)
            next_offset = offset + len(data.get("data", []))
            next_token = str(next_offset) if next_offset < total else None

            return files, next_token

    def _get_mime_type(self, extension: str) -> str:
        """Get MIME type from extension."""
        mime_map = {
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "txt": "text/plain",
            "rtf": "application/rtf",
            "xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "msg": "application/vnd.ms-outlook",
            "eml": "message/rfc822",
        }
        return mime_map.get(extension, "application/octet-stream")

    async def download_file(self, file_id: str) -> bytes:
        """Download a file from iManage."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient() as client:
            return await self._download_capped(
                client,
                "GET",
                f"{self._get_api_url()}/documents/{quote(file_id, safe='')}/download",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
            )


imanage_connector = IManageConnector()
