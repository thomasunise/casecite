"""
Tests for right-to-erasure / data-export document-service helpers.

Imports document_service (which pulls the RAG/vector stack), so these run in CI
where chromadb is installed; skipped locally when it isn't.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import pytest

pytest.importorskip("chromadb")

from datetime import UTC, datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from app.models.schemas import ConnectorType, Document, DocumentStatus  # noqa: E402
from app.services import user_settings as user_settings_module  # noqa: E402
from app.services.connectors import base as connectors_base  # noqa: E402
from app.services.connectors.base import BaseConnector, delete_user_credentials  # noqa: E402
from app.services.documents import document_service  # noqa: E402
from app.services.user_settings import (  # noqa: E402
    delete_user_settings,
    load_user_settings,
    save_user_settings,
)


def _make_doc(doc_id: str, user_id: str) -> Document:
    return Document(
        id=doc_id,
        filename=f"{doc_id}.pdf",
        user_id=user_id,
        content_type="application/pdf",
        size=4,
        source=ConnectorType.LOCAL,
        status=DocumentStatus.INDEXED,
        created_at=datetime.now(UTC),
    )


class TestExportUserData:
    def test_export_only_includes_owner_documents(self):
        document_service.documents["exp-a"] = _make_doc("exp-a", "owner")
        document_service.documents["exp-b"] = _make_doc("exp-b", "other")
        try:
            export = document_service.export_user_data("owner")
            ids = {d["id"] for d in export["documents"]}
            assert "exp-a" in ids
            assert "exp-b" not in ids
        finally:
            document_service.documents.pop("exp-a", None)
            document_service.documents.pop("exp-b", None)

    def test_export_shape(self):
        export = document_service.export_user_data("nobody")
        assert "documents" in export
        assert "folders" in export
        assert export["documents"] == []


def _write_credentials(upload_dir: str, connector_type: ConnectorType, user_id: str, creds: dict):
    path = os.path.join(upload_dir, f"credentials_{connector_type.value}_{user_id}.json")
    BaseConnector._write_credentials_file(path, creds)
    assert os.path.exists(path)
    return path


def _mock_http(status_code: int = 200):
    """An httpx.AsyncClient stand-in whose post() returns *status_code*."""
    response = MagicMock()
    response.status_code = status_code
    response.is_success = 200 <= status_code < 300
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm), client


class TestDeleteUserCredentials:
    """Right-to-erasure must remove every connector OAuth token file."""

    @pytest.mark.asyncio
    async def test_all_connector_files_removed_and_counted(self, tmp_path):
        user = "erase-me"
        with patch.object(connectors_base, "settings", SimpleNamespace(upload_dir=str(tmp_path))):
            paths = [
                _write_credentials(str(tmp_path), ct, user, {"access_token": f"tok-{ct.value}"})
                for ct in (ConnectorType.BOX, ConnectorType.CLIO, ConnectorType.ONEDRIVE)
            ]
            other = _write_credentials(str(tmp_path), ConnectorType.BOX, "someone-else", {"a": 1})

            result = await delete_user_credentials(user)

        assert result == {"connector_credentials_deleted": 3, "connector_tokens_revoked": 0}
        assert not any(os.path.exists(p) for p in paths)
        assert os.path.exists(other)  # other users are untouched

    @pytest.mark.asyncio
    async def test_nothing_to_delete_is_zero(self, tmp_path):
        with patch.object(connectors_base, "settings", SimpleNamespace(upload_dir=str(tmp_path))):
            assert await delete_user_credentials("nobody") == {
                "connector_credentials_deleted": 0,
                "connector_tokens_revoked": 0,
            }

    @pytest.mark.asyncio
    async def test_google_and_dropbox_tokens_are_revoked_before_deletion(self, tmp_path):
        user = "u1"
        factory, http = _mock_http(200)
        with (
            patch.object(connectors_base, "settings", SimpleNamespace(upload_dir=str(tmp_path))),
            patch.object(connectors_base.httpx, "AsyncClient", factory),
        ):
            g = _write_credentials(
                str(tmp_path),
                ConnectorType.GOOGLE_DRIVE,
                user,
                {"access_token": "g-access", "refresh_token": "g-refresh"},
            )
            d = _write_credentials(
                str(tmp_path), ConnectorType.DROPBOX, user, {"access_token": "d-access"}
            )
            result = await delete_user_credentials(user)

        assert result == {"connector_credentials_deleted": 2, "connector_tokens_revoked": 2}
        assert not os.path.exists(g) and not os.path.exists(d)
        calls = {c.args[0]: c.kwargs for c in http.post.call_args_list}
        assert calls["https://oauth2.googleapis.com/revoke"]["data"] == {"token": "g-refresh"}
        assert calls["https://api.dropboxapi.com/2/auth/token/revoke"]["headers"] == {
            "Authorization": "Bearer d-access"
        }

    @pytest.mark.asyncio
    async def test_revocation_failure_still_deletes_file(self, tmp_path):
        user = "u2"
        factory, http = _mock_http(400)
        with (
            patch.object(connectors_base, "settings", SimpleNamespace(upload_dir=str(tmp_path))),
            patch.object(connectors_base.httpx, "AsyncClient", factory),
        ):
            g = _write_credentials(
                str(tmp_path), ConnectorType.GOOGLE_DRIVE, user, {"access_token": "g-access"}
            )
            result = await delete_user_credentials(user)
        assert result == {"connector_credentials_deleted": 1, "connector_tokens_revoked": 0}
        assert not os.path.exists(g)

    @pytest.mark.asyncio
    async def test_revocation_network_error_is_swallowed(self, tmp_path):
        import httpx

        user = "u3"
        factory, http = _mock_http(200)
        http.post = AsyncMock(side_effect=httpx.ConnectError("boom"))
        with (
            patch.object(connectors_base, "settings", SimpleNamespace(upload_dir=str(tmp_path))),
            patch.object(connectors_base.httpx, "AsyncClient", factory),
        ):
            d = _write_credentials(
                str(tmp_path), ConnectorType.DROPBOX, user, {"access_token": "d-access"}
            )
            result = await delete_user_credentials(user)
        assert result["connector_credentials_deleted"] == 1
        assert result["connector_tokens_revoked"] == 0
        assert not os.path.exists(d)

    @pytest.mark.asyncio
    async def test_in_process_cache_is_dropped(self, tmp_path):
        from app.services.connectors import CONNECTORS

        user = "cached-user"
        box = CONNECTORS[ConnectorType.BOX]
        box._credentials_cache[user] = {"access_token": "stale"}
        try:
            with patch.object(
                connectors_base, "settings", SimpleNamespace(upload_dir=str(tmp_path))
            ):
                await delete_user_credentials(user)
            assert user not in box._credentials_cache
        finally:
            box._credentials_cache.pop(user, None)


class TestDeleteUserSettings:
    def test_settings_file_removed(self, tmp_path):
        from app.models.schemas import RAGSettings

        with patch.object(user_settings_module, "SETTINGS_DIR", str(tmp_path)):
            save_user_settings("erase-me", RAGSettings())
            assert os.path.exists(tmp_path / "rag_settings_erase-me.json")
            assert delete_user_settings("erase-me") == 1
            assert not os.path.exists(tmp_path / "rag_settings_erase-me.json")
            # Back to defaults, not an error.
            assert load_user_settings("erase-me") == RAGSettings()

    def test_missing_file_is_zero(self, tmp_path):
        with patch.object(user_settings_module, "SETTINGS_DIR", str(tmp_path)):
            assert delete_user_settings("nobody") == 0


class TestDeleteUserRouteWiring:
    """delete_user must call the new erasure helpers and report their counts."""

    def test_route_calls_credential_and_settings_erasure(self):
        import inspect

        from app.routers import users as users_router

        src = inspect.getsource(users_router.delete_user)
        # Counts flow into the audit-event details via purge_result.
        assert "purge_result.update(await delete_user_credentials(user_id))" in src
        assert 'purge_result["settings_files_deleted"] = delete_user_settings(user_id)' in src
