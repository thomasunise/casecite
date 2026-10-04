from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from app.config import settings
from app.models.schemas import ConnectorType
from app.services import connector_credentials
from app.services.connectors.base import BaseConnector, ConnectorError, FileInfo

GRAPH = "https://graph.microsoft.com/v1.0"


def _seg(value: str) -> str:
    """Percent-encode an id for use as a single Graph URL path segment."""
    return quote(value, safe="!")


class MicrosoftConnector(BaseConnector):
    """Microsoft OneDrive/SharePoint connector using OAuth 2.0.

    A full-account crawl covers the personal OneDrive plus every SharePoint
    site drive the account can reach; a folder-scoped crawl starts at the
    given item, drive ("drive:{driveId}") or composite id instead. Items
    outside the personal drive use composite ids ("drv:{driveId}:{itemId}")
    so listing and download know which drive to hit.

    Scopes are read-only: the connector only lists and downloads.
    """

    connector_type = ConnectorType.ONEDRIVE

    @property
    def is_configured(self) -> bool:
        return bool(
            connector_credentials.get("microsoft_client_id")
            and connector_credentials.get("microsoft_client_secret")
        )

    SCOPES = [
        "Files.Read.All",
        "Sites.Read.All",
        "User.Read",
        "offline_access",
    ]

    def get_auth_url(self, state: str) -> str:
        """Get Microsoft OAuth authorization URL."""
        params = {
            "client_id": connector_credentials.get("microsoft_client_id"),
            "redirect_uri": settings.microsoft_redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "response_mode": "query",
            "state": state,
        }
        tenant = connector_credentials.get("microsoft_tenant_id") or "common"
        return (
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{urlencode(params)}"
        )

    async def handle_callback(self, code: str, state: str) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        tenant = connector_credentials.get("microsoft_tenant_id") or "common"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                data={
                    "client_id": connector_credentials.get("microsoft_client_id"),
                    "client_secret": connector_credentials.get("microsoft_client_secret"),
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.microsoft_redirect_uri,
                    "scope": " ".join(self.SCOPES),
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
            tenant = connector_credentials.get("microsoft_tenant_id") or "common"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                    data={
                        "client_id": connector_credentials.get("microsoft_client_id"),
                        "client_secret": connector_credentials.get("microsoft_client_secret"),
                        "refresh_token": self.credentials["refresh_token"],
                        "grant_type": "refresh_token",
                        "scope": " ".join(self.SCOPES),
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
        """Get Microsoft account information."""
        await self._ensure_valid_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
            )
            response.raise_for_status()
            data = response.json()

            return {
                "name": data.get("displayName"),
                "email": data.get("mail") or data.get("userPrincipalName"),
            }

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.credentials['access_token']}"}

    @staticmethod
    def _split_composite_id(file_id: str) -> tuple[str | None, str]:
        """Split "drv:{driveId}:{itemId}" into (driveId, itemId).

        Plain ids (personal OneDrive) return (None, id).
        """
        if file_id and file_id.startswith("drv:"):
            _, drive_id, item_id = file_id.split(":", 2)
            return drive_id, item_id
        return None, file_id

    def _item_to_fileinfo(self, item: dict[str, Any], drive_id: str | None) -> FileInfo:
        if "folder" in item:
            mime_type = "folder"
        elif "file" in item:
            mime_type = item["file"].get("mimeType", "application/octet-stream")
        else:
            mime_type = "application/octet-stream"

        item_id = item["id"] if drive_id is None else f"drv:{drive_id}:{item['id']}"

        return FileInfo(
            id=item_id,
            name=item["name"],
            mime_type=mime_type,
            size=item.get("size", 0),
            modified_at=datetime.fromisoformat(item["lastModifiedDateTime"].replace("Z", "+00:00")),
            path=item.get("parentReference", {}).get("path", ""),
            download_url=item.get("@microsoft.graph.downloadUrl"),
            metadata={"webUrl": item.get("webUrl")},
        )

    async def _list_site_drives(self, client: httpx.AsyncClient) -> list[FileInfo]:
        """Enumerate SharePoint site drives as synthetic folder entries."""
        drives: list[FileInfo] = []
        try:
            sites_resp = await client.get(
                f"{GRAPH}/sites",
                headers=self._auth_headers(),
                params={"search": "*", "$select": "id,displayName"},
            )
            sites_resp.raise_for_status()
            sites = sites_resp.json().get("value", [])
        except httpx.HTTPError:
            # Personal accounts have no /sites — the personal drive still syncs.
            return drives

        for site in sites:
            site_id = site.get("id")
            if not site_id:
                continue
            try:
                drives_resp = await client.get(
                    f"{GRAPH}/sites/{site_id}/drives",
                    headers=self._auth_headers(),
                    params={"$select": "id,name"},
                )
                drives_resp.raise_for_status()
            except httpx.HTTPError:  # nosec B112 - inaccessible site, keep crawling the rest
                continue

            for drive in drives_resp.json().get("value", []):
                drive_id = drive.get("id")
                if not drive_id:
                    continue
                drives.append(
                    FileInfo(
                        id=f"drive:{drive_id}",
                        name=f"{site.get('displayName', 'SharePoint')} — {drive.get('name', 'Documents')}",
                        mime_type="folder",
                        size=0,
                        modified_at=datetime.now(UTC),
                        metadata={"kind": "sharepoint_drive", "site": site.get("displayName")},
                    )
                )
        return drives

    async def list_files(
        self, folder_id: str | None = None, page_token: str | None = None
    ) -> tuple[list[FileInfo], str | None]:
        """List files in OneDrive and SharePoint site drives.

        Root listing = personal OneDrive root children plus one synthetic
        folder per SharePoint site drive. Page tokens are "{driveId}|{url}"
        so pagination keeps its drive context.
        """
        await self._ensure_valid_token()

        drive_ctx: str | None = None
        include_site_drives = False

        if page_token:
            drive_part, url = page_token.split("|", 1)
            drive_ctx = drive_part or None
        elif folder_id is None:
            url = f"{GRAPH}/me/drive/root/children"
            include_site_drives = True
        elif folder_id.startswith("drive:"):
            drive_ctx = folder_id.removeprefix("drive:")
            url = f"{GRAPH}/drives/{_seg(drive_ctx)}/root/children"
        elif folder_id.startswith("drv:"):
            drive_ctx, item_id = self._split_composite_id(folder_id)
            url = f"{GRAPH}/drives/{_seg(drive_ctx)}/items/{_seg(item_id)}/children"
        else:
            url = f"{GRAPH}/me/drive/items/{_seg(folder_id)}/children"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self._auth_headers(),
                params={"$top": 100} if not page_token else None,
            )
            response.raise_for_status()
            data = response.json()

            files = [self._item_to_fileinfo(item, drive_ctx) for item in data.get("value", [])]

            if include_site_drives:
                files.extend(await self._list_site_drives(client))

            next_link = data.get("@odata.nextLink")
            next_token = f"{drive_ctx or ''}|{next_link}" if next_link else None
            return files, next_token

    async def download_file(self, file_id: str) -> bytes:
        """Download a file from OneDrive or a SharePoint site drive."""
        await self._ensure_valid_token()

        drive_id, item_id = self._split_composite_id(file_id)
        if drive_id:
            item_url = f"{GRAPH}/drives/{_seg(drive_id)}/items/{_seg(item_id)}"
        else:
            item_url = f"{GRAPH}/me/drive/items/{_seg(item_id)}"

        async with httpx.AsyncClient() as client:
            # Get download URL
            response = await client.get(
                item_url,
                headers=self._auth_headers(),
                params={"select": "@microsoft.graph.downloadUrl"},
            )
            response.raise_for_status()
            download_url = response.json().get("@microsoft.graph.downloadUrl")

            if not download_url:
                raise ConnectorError("No download URL available")

            # Download the file (pre-authenticated URL; no bearer token sent)
            return await self._download_capped(client, "GET", download_url)


microsoft_connector = MicrosoftConnector()
