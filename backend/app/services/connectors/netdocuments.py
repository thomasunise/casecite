import base64
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from app.config import settings
from app.models.schemas import ConnectorType
from app.services.connectors.base import BaseConnector, ConnectorError, FileInfo


class NetDocumentsConnector(BaseConnector):
    """NetDocuments connector using OAuth 2.0.

    NOT VALIDATED AGAINST A LIVE TENANT. The endpoint paths used here (the
    cabinet listing, cabinet folders, folder contents and document content
    routes) were written from NetDocuments' published API shape and are
    exercised only by mocked unit tests; no real NetDocuments repository has
    been used to confirm them. Treat this connector as experimental until it
    has been run against your repository.
    """

    connector_type = ConnectorType.NETDOCUMENTS

    @property
    def is_configured(self) -> bool:
        return bool(settings.netdocuments_client_id and settings.netdocuments_client_secret)

    @property
    def api_base(self) -> str:
        return f"{settings.netdocuments_api_host}/v2"

    @property
    def _token_url(self) -> str:
        return f"{settings.netdocuments_api_host}/v1/OAuth"

    def get_auth_url(self, state: str) -> str:
        """Get NetDocuments OAuth authorization URL.

        Authorization is a browser page on the vault host, not the API host.
        """
        params = {
            "client_id": settings.netdocuments_client_id,
            "redirect_uri": settings.netdocuments_redirect_uri,
            "response_type": "code",
            "scope": "read",
            "state": state,
        }
        return f"{settings.netdocuments_vault_host}/neWeb2/OAuth.aspx?{urlencode(params)}"

    async def handle_callback(self, code: str, state: str) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        # NetDocuments uses Basic auth for token endpoint
        auth_string = f"{settings.netdocuments_client_id}:{settings.netdocuments_client_secret}"
        auth_header = base64.b64encode(auth_string.encode()).decode()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._token_url,
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.netdocuments_redirect_uri,
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
            auth_string = f"{settings.netdocuments_client_id}:{settings.netdocuments_client_secret}"
            auth_header = base64.b64encode(auth_string.encode()).decode()

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._token_url,
                    headers={
                        "Authorization": f"Basic {auth_header}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self.credentials["refresh_token"],
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
            raise ConnectorError("Not authenticated")

        expires_at = self.credentials.get("expires_at", 0)
        if datetime.now(UTC).timestamp() >= expires_at - 60:
            if not await self.refresh_token():
                raise ConnectorError("Failed to refresh token")

    async def get_account_info(self) -> dict[str, Any]:
        """Get NetDocuments account information."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/User/info",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
            )
            response.raise_for_status()
            data = response.json()

            return {
                "name": data.get("displayName", ""),
                "email": data.get("email", ""),
                "repository": data.get("repository", {}).get("name", ""),
            }

    async def list_cabinets(self) -> list[dict[str, Any]]:
        """List available cabinets (top-level containers)."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/Cabinet",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
            )
            response.raise_for_status()
            return response.json().get("cabinets", [])

    async def list_files(
        self, folder_id: str | None = None, page_token: str | None = None
    ) -> tuple[list[FileInfo], str | None]:
        """List files in NetDocuments.

        The root listing emits every cabinet as a folder entry so the crawl
        covers the whole repository instead of silently stopping at the first
        cabinet. Cabinet ids are prefixed so the next level knows to list the
        cabinet's top-level folders rather than folder contents.
        """
        await self._ensure_valid_token()

        if not folder_id:
            cabinets = await self.list_cabinets()
            return [
                FileInfo(
                    id=f"cabinet:{cab.get('id', '')}",
                    name=cab.get("name", ""),
                    mime_type="folder",
                    size=0,
                    modified_at=datetime.now(UTC),
                    metadata={"kind": "cabinet"},
                )
                for cab in cabinets
                if cab.get("id")
            ], None

        if folder_id.startswith("cabinet:"):
            return await self._list_cabinet_folders(folder_id.removeprefix("cabinet:"))

        params = {"$top": 100}
        if page_token:
            params["$skip"] = int(page_token)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/Folder/{quote(folder_id, safe='')}/contents",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            files = []
            for item in data.get("list", []):
                item_type = item.get("type", "")

                if item_type == "folder":
                    mime_type = "folder"
                else:
                    mime_type = item.get("mimeType", self._get_mime_type(item.get("name", "")))

                modified = item.get("modified", {})
                modified_at = datetime.now(UTC)
                if modified.get("date"):
                    try:
                        modified_at = datetime.fromisoformat(
                            modified["date"].replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass

                files.append(
                    FileInfo(
                        id=item.get("id", ""),
                        name=item.get("name", ""),
                        mime_type=mime_type,
                        size=item.get("size", 0),
                        modified_at=modified_at,
                        metadata={
                            "cabinet": item.get("cabinet"),
                            "version": item.get("version"),
                            "extension": item.get("extension"),
                        },
                    )
                )

            # Pagination
            total = data.get("total", 0)
            current_skip = int(page_token) if page_token else 0
            next_skip = current_skip + len(data.get("list", []))
            next_token = str(next_skip) if next_skip < total else None

            return files, next_token

    async def _list_cabinet_folders(self, cabinet_id: str) -> tuple[list[FileInfo], str | None]:
        """List a cabinet's top-level folders as folder entries."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/Cabinet/{quote(cabinet_id, safe='')}/folders",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("list", data if isinstance(data, list) else [])

            return [
                FileInfo(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    mime_type="folder",
                    size=0,
                    modified_at=datetime.now(UTC),
                    metadata={"cabinet": cabinet_id},
                )
                for item in items
                if item.get("id")
            ], None

    def _get_mime_type(self, filename: str) -> str:
        """Infer MIME type from filename."""
        ext = filename.lower().split(".")[-1] if "." in filename else ""
        mime_map = {
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "txt": "text/plain",
            "rtf": "application/rtf",
        }
        return mime_map.get(ext, "application/octet-stream")

    async def download_file(self, file_id: str) -> bytes:
        """Download a file from NetDocuments."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient() as client:
            return await self._download_capped(
                client,
                "GET",
                f"{self.api_base}/Document/{quote(file_id, safe='')}/content",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
            )


netdocuments_connector = NetDocumentsConnector()
