"""
Unit tests for connector-internal logic added in the connector completeness pass:
Microsoft composite drive ids, Clio registration and OAuth URLs, NetDocuments
region hosts, and Filevine configuration semantics.

Settings is frozen, so tests swap each connector module's `settings` reference
for a SimpleNamespace instead of patching attributes.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

import httpx
import pytest
from app.models.schemas import ConnectorType
from app.services.connectors import CONNECTORS
from app.services.connectors.base import (
    BaseConnector,
    ConnectorError,
    FileInfo,
    FileTooLargeError,
)
from app.services.connectors.clio import ClioConnector
from app.services.connectors.microsoft import MicrosoftConnector
from app.services.connectors.netdocuments import NetDocumentsConnector


@contextmanager
def _mock_transport(handler):
    """Route every httpx.AsyncClient the connectors create through *handler*."""
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    with patch("httpx.AsyncClient", side_effect=factory):
        yield


class TestMicrosoftCompositeIds:
    """SharePoint items ride composite ids so the drive context survives."""

    def test_plain_id_passes_through(self):
        drive_id, item_id = MicrosoftConnector._split_composite_id("ABC123")
        assert drive_id is None
        assert item_id == "ABC123"

    def test_composite_id_splits(self):
        drive_id, item_id = MicrosoftConnector._split_composite_id("drv:b!xyz:01ITEM")
        assert drive_id == "b!xyz"
        assert item_id == "01ITEM"

    def test_composite_id_with_colons_in_item(self):
        drive_id, item_id = MicrosoftConnector._split_composite_id("drv:d1:item:with:colons")
        assert drive_id == "d1"
        assert item_id == "item:with:colons"

    def test_sharepoint_scope_requested(self):
        assert "Sites.Read.All" in MicrosoftConnector.SCOPES

    def test_scopes_are_read_only(self):
        """The crawl only lists and downloads; no write scope is requested."""
        assert "Files.Read.All" in MicrosoftConnector.SCOPES
        assert not any("Write" in scope for scope in MicrosoftConnector.SCOPES)


class TestClioConnector:
    """Clio is a first-class connector now."""

    def test_registered(self):
        assert ConnectorType.CLIO in CONNECTORS

    def test_auth_url(self):
        connector = ClioConnector()
        fake = SimpleNamespace(
            clio_client_id="cid",
            clio_client_secret="sec",
            clio_base_url="https://app.clio.com",
            clio_redirect_uri="https://x/cb",
        )
        with patch("app.services.connectors.clio.settings", fake):
            url = connector.get_auth_url("state123")
        assert url.startswith("https://app.clio.com/oauth/authorize?")
        assert "client_id=cid" in url
        assert "state=state123" in url

    def test_unconfigured_without_credentials(self):
        connector = ClioConnector()
        fake = SimpleNamespace(
            clio_client_id=None,
            clio_client_secret=None,
            clio_base_url="https://app.clio.com",
            clio_redirect_uri="",
        )
        with patch("app.services.connectors.clio.settings", fake):
            assert connector.is_configured is False


class TestNetDocumentsHosts:
    """Authorize is a browser page on the vault host; the API host serves data."""

    def _fake_settings(self):
        return SimpleNamespace(
            netdocuments_client_id="cid",
            netdocuments_client_secret="sec",
            netdocuments_redirect_uri="https://x/cb",
            netdocuments_vault_host="https://vault.netvoyage.com",
            netdocuments_api_host="https://api.vault.netvoyage.com",
        )

    def test_auth_url_uses_vault_host(self):
        connector = NetDocumentsConnector()
        with patch("app.services.connectors.netdocuments.settings", self._fake_settings()):
            url = connector.get_auth_url("s")
        assert url.startswith("https://vault.netvoyage.com/neWeb2/OAuth.aspx?")

    def test_api_base_uses_api_host(self):
        connector = NetDocumentsConnector()
        with patch("app.services.connectors.netdocuments.settings", self._fake_settings()):
            assert connector.api_base == "https://api.vault.netvoyage.com/v2"


class TestFilevineConfiguration:
    """Filevine needs key + secret, and an explicit admin opt-in (firm-wide key)."""

    def _fake_settings(self, key, secret, enabled=True):
        return SimpleNamespace(
            filevine_enabled=enabled,
            filevine_api_key=key,
            filevine_api_secret=secret,
            filevine_base_url="https://api.filevine.io",
        )

    def test_requires_both_key_and_secret(self):
        from app.services.connectors.filevine import FilevineConnector

        connector = FilevineConnector()
        with patch("app.services.connectors.filevine.settings", self._fake_settings("k", None)):
            assert connector.is_configured is False
        with patch("app.services.connectors.filevine.settings", self._fake_settings("k", "s")):
            assert connector.is_configured is True

    def test_key_alone_does_not_enable_it(self):
        """A configured key must not make the connector live without the opt-in."""
        from app.services.connectors.filevine import FilevineConnector

        connector = FilevineConnector()
        with patch(
            "app.services.connectors.filevine.settings",
            self._fake_settings("k", "s", enabled=False),
        ):
            assert connector.is_configured is False
            assert connector.is_connected is False

    def test_is_admin_only(self):
        from app.services.connectors.filevine import FilevineConnector

        assert FilevineConnector.requires_admin is True
        assert MicrosoftConnector.requires_admin is False


class TestGoogleScopes:
    def test_no_redundant_or_write_scope(self):
        from app.services.connectors.google_drive import GoogleDriveConnector

        scopes = GoogleDriveConnector.SCOPES
        assert "https://www.googleapis.com/auth/drive.readonly" in scopes
        assert "https://www.googleapis.com/auth/drive.file" not in scopes
        assert "https://www.googleapis.com/auth/drive" not in scopes

    async def test_folder_id_is_escaped_in_query(self):
        """A caller-supplied folder id cannot break out of the Drive query string."""
        from app.services.connectors.google_drive import GoogleDriveConnector

        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["q"] = request.url.params["q"]
            return httpx.Response(200, json={"files": []})

        connector = GoogleDriveConnector()
        with (
            patch.object(GoogleDriveConnector, "_ensure_valid_token", AsyncMock()),
            patch.object(
                GoogleDriveConnector,
                "credentials",
                new_callable=PropertyMock,
                return_value={"access_token": "tok"},
            ),
            _mock_transport(handler),
        ):
            await connector.list_files("x' or name contains 'secret")

        assert seen["q"] == "trashed = false and 'x\\' or name contains \\'secret' in parents"


class _ListingConnector(ClioConnector):
    """Concrete connector with an in-memory folder tree, for crawl tests."""

    supports_folder_sync = True
    TREE = {
        None: [("root.pdf", "application/pdf"), ("matter-a", "folder"), ("matter-b", "folder")],
        "matter-a": [("a1.pdf", "application/pdf"), ("a2.png", "image/png")],
        "matter-b": [("b1.pdf", "application/pdf")],
    }

    async def list_files(self, folder_id=None, page_token=None):
        return [
            FileInfo(id=name, name=name, mime_type=mime, size=1, modified_at=datetime.now(UTC))
            for name, mime in self.TREE[folder_id]
        ], None


class TestFolderScopedCrawl:
    """A sync of one folder must not walk the rest of the account."""

    async def test_crawl_starts_at_folder(self):
        names = [f.name async for f in _ListingConnector().crawl_all_files(folder_id="matter-a")]
        assert names == ["a1.pdf"]

    async def test_crawl_without_folder_covers_everything(self):
        names = [f.name async for f in _ListingConnector().crawl_all_files()]
        assert names == ["root.pdf", "a1.pdf", "b1.pdf"]

    async def test_flat_connector_refuses_a_folder(self):
        """Clio's listing is account-wide; a folder must be refused, not ignored."""
        connector = ClioConnector()
        assert connector.supports_folder_sync is False
        with pytest.raises(ConnectorError):
            async for _ in connector.crawl_all_files(folder_id="123"):
                pass
        with pytest.raises(ConnectorError):
            await connector.list_files(folder_id="123")


class TestDownloadCap:
    """Connector downloads are size-capped while streaming."""

    async def _download(self, handler, max_bytes=10):
        connector = ClioConnector()
        fake = SimpleNamespace(max_upload_size=max_bytes)
        with patch("app.services.connectors.base.settings", fake):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await connector._download_capped(client, "GET", "https://files.test/x")

    async def test_small_body_is_returned(self):
        assert await self._download(lambda r: httpx.Response(200, content=b"12345")) == b"12345"

    async def test_declared_oversize_is_refused(self):
        with pytest.raises(FileTooLargeError):
            await self._download(lambda r: httpx.Response(200, content=b"x" * 11))

    async def test_undeclared_oversize_is_refused_while_streaming(self):
        async def body():
            for _ in range(5):
                yield b"xxxx"

        with pytest.raises(FileTooLargeError):
            await self._download(lambda r: httpx.Response(200, content=body()))

    async def test_http_error_propagates(self):
        with pytest.raises(httpx.HTTPStatusError):
            await self._download(lambda r: httpx.Response(403))

    async def test_dropbox_path_is_json_encoded(self):
        """Quotes and non-ASCII in a path must not corrupt the API-Arg header."""
        from app.services.connectors.dropbox import DropboxConnector

        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["arg"] = request.headers["Dropbox-API-Arg"]
            return httpx.Response(200, content=b"ok")

        with (
            patch.object(DropboxConnector, "_ensure_valid_token", AsyncMock()),
            patch.object(
                DropboxConnector,
                "credentials",
                new_callable=PropertyMock,
                return_value={"access_token": "tok"},
            ),
            _mock_transport(handler),
        ):
            await DropboxConnector().download_file('/a "b"/é.pdf')

        assert json.loads(seen["arg"]) == {"path": '/a "b"/é.pdf'}
        assert seen["arg"].isascii()


class TestCredentialIsolation:
    """Credential files are per-user; a legacy global file is never adopted."""

    def _settings(self, tmp_path):
        return SimpleNamespace(upload_dir=str(tmp_path))

    def test_legacy_global_file_is_not_claimed(self, tmp_path):
        connector = ClioConnector()
        with patch("app.services.connectors.base.settings", self._settings(tmp_path)):
            legacy = tmp_path / "credentials_clio.json"
            connector._write_credentials_file(str(legacy), {"access_token": "someone-elses"})

            BaseConnector.set_current_user("user-a")
            assert connector.credentials == {}
            assert connector.is_connected is False
            # Left in place for an administrator to remove, and not copied.
            assert legacy.exists()
            assert not (tmp_path / "credentials_clio_user-a.json").exists()

    def test_user_scoped_file_is_loaded(self, tmp_path):
        connector = ClioConnector()
        with patch("app.services.connectors.base.settings", self._settings(tmp_path)):
            BaseConnector.set_current_user("user-a")
            connector.credentials = {"access_token": "mine"}
            connector._save_credentials()

            fresh = ClioConnector()
            assert fresh.credentials == {"access_token": "mine"}
            BaseConnector.set_current_user("user-b")
            assert fresh.credentials == {}


class TestDisconnectRevokes:
    """Disconnect revokes at the provider when it can, and always clears locally."""

    async def test_box_token_is_revoked(self, tmp_path):
        from app.services.connectors.box import BoxConnector

        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((str(request.url), request.content.decode()))
            return httpx.Response(200)

        connector = BoxConnector()
        with (
            patch(
                "app.services.connectors.base.settings", SimpleNamespace(upload_dir=str(tmp_path))
            ),
            patch(
                "app.services.connector_credentials.get",
                side_effect={"box_client_id": "cid", "box_client_secret": "sec"}.get,
            ),
            _mock_transport(handler),
        ):
            BaseConnector.set_current_user("user-a")
            connector.credentials = {"access_token": "at", "refresh_token": "rt"}
            connector._save_credentials()

            await connector.disconnect()

            assert connector.credentials == {}
            assert not (tmp_path / "credentials_box_user-a.json").exists()

        assert len(calls) == 1
        url, body = calls[0]
        assert url == "https://api.box.com/oauth2/revoke"
        assert "token=rt" in body

    async def test_provider_failure_does_not_block_local_deletion(self, tmp_path):
        from app.services.connectors.dropbox import DropboxConnector

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("provider down")

        connector = DropboxConnector()
        with (
            patch(
                "app.services.connectors.base.settings", SimpleNamespace(upload_dir=str(tmp_path))
            ),
            _mock_transport(handler),
        ):
            BaseConnector.set_current_user("user-a")
            connector.credentials = {"access_token": "at"}
            connector._save_credentials()

            await connector.disconnect()

            assert connector.credentials == {}
            assert not (tmp_path / "credentials_dropbox_user-a.json").exists()


class TestUnvalidatedConnectorsAreLabelled:
    """iManage/NetDocuments have never run against a live tenant; say so in the code."""

    def test_docstrings_carry_the_warning(self):
        from app.services.connectors.imanage import IManageConnector

        for cls in (IManageConnector, NetDocumentsConnector):
            assert "NOT VALIDATED AGAINST A LIVE TENANT" in cls.__doc__
