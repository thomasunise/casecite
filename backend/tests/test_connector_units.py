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

from types import SimpleNamespace
from unittest.mock import patch

from app.models.schemas import ConnectorType
from app.services.connectors import CONNECTORS
from app.services.connectors.clio import ClioConnector
from app.services.connectors.microsoft import MicrosoftConnector
from app.services.connectors.netdocuments import NetDocumentsConnector


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
    """Filevine needs both key and secret for the signed session handshake."""

    def _fake_settings(self, key, secret):
        return SimpleNamespace(
            filevine_api_key=key,
            filevine_api_secret=secret,
            filevine_base_url="https://api.filevine.io",
        )

    def test_requires_both_key_and_secret(self):
        from app.services.connectors.filevine import FilevineConnector

        connector = FilevineConnector()
        with patch(
            "app.services.connectors.filevine.settings", self._fake_settings("k", None)
        ):
            assert connector.is_configured is False
        with patch(
            "app.services.connectors.filevine.settings", self._fake_settings("k", "s")
        ):
            assert connector.is_configured is True
