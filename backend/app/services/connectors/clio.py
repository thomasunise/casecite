from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from app.config import settings
from app.models.schemas import ConnectorType
from app.services.connectors.base import BaseConnector, ConnectorError, FileInfo


class ClioConnector(BaseConnector):
    """Clio practice-management connector using OAuth 2.0.

    Documents are listed flat via the v4 documents endpoint (Clio's own
    pagination), so the crawl needs no folder recursion. That also means a
    sync cannot be limited to one folder: a folder-scoped sync is refused and
    only an explicit full-account sync is available.
    """

    connector_type = ConnectorType.CLIO
    supports_folder_sync = False

    @property
    def is_configured(self) -> bool:
        return bool(settings.clio_client_id and settings.clio_client_secret)

    @property
    def _base(self) -> str:
        return settings.clio_base_url.rstrip("/")

    @property
    def _api(self) -> str:
        return f"{self._base}/api/v4"

    def get_auth_url(self, state: str) -> str:
        """Get Clio OAuth authorization URL."""
        params = {
            "client_id": settings.clio_client_id,
            "redirect_uri": settings.clio_redirect_uri,
            "response_type": "code",
            "state": state,
        }
        return f"{self._base}/oauth/authorize?{urlencode(params)}"

    async def handle_callback(self, code: str, state: str) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base}/oauth/token",
                data={
                    "client_id": settings.clio_client_id,
                    "client_secret": settings.clio_client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.clio_redirect_uri,
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
                    f"{self._base}/oauth/token",
                    data={
                        "client_id": settings.clio_client_id,
                        "client_secret": settings.clio_client_secret,
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

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.credentials['access_token']}"}

    async def get_account_info(self) -> dict[str, Any]:
        """Get Clio account information."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._api}/users/who_am_i.json",
                headers=self._auth_headers(),
                params={"fields": "id,name,email"},
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
        """List documents in Clio.

        Clio's v4 pagination hands back a full next-page URL in
        meta.paging.next; that URL is used verbatim as the page token.
        The listing is flat and account-wide, so a folder_id is rejected
        rather than silently ignored.
        """
        if folder_id:
            raise ConnectorError("Clio cannot list a single folder")
        await self._ensure_valid_token()

        if page_token:
            url = page_token
            params = None
        else:
            url = f"{self._api}/documents.json"
            params = {
                "fields": "id,name,content_type,size,updated_at,matter{id,display_number}",
                "limit": 100,
                "order": "id(asc)",
            }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self._auth_headers(), params=params)
            response.raise_for_status()
            payload = response.json()

            files = []
            for item in payload.get("data", []):
                updated = item.get("updated_at", "")
                modified_at = datetime.now(UTC)
                if updated:
                    try:
                        modified_at = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                matter = item.get("matter") or {}
                files.append(
                    FileInfo(
                        id=str(item.get("id", "")),
                        name=item.get("name", ""),
                        mime_type=item.get("content_type", "application/octet-stream"),
                        size=item.get("size", 0),
                        modified_at=modified_at,
                        # Namespaced: a bare "matter_id" would collide with
                        # CaseCite's own matter (access-scope) field downstream.
                        metadata={
                            "clio_matter_id": matter.get("id"),
                            "clio_matter": matter.get("display_number"),
                        },
                    )
                )

            next_url = payload.get("meta", {}).get("paging", {}).get("next")
            return files, next_url

    async def download_file(self, file_id: str) -> bytes:
        """Download a document from Clio (302s to blob storage)."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient(follow_redirects=True) as client:
            return await self._download_capped(
                client,
                "GET",
                f"{self._api}/documents/{quote(file_id, safe='')}/download",
                headers=self._auth_headers(),
            )


clio_connector = ClioConnector()
