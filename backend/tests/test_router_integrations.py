"""HTTP-level tests for the admin integrations router (/api/v1/admin/integrations).

Instance-wide credentials: every route must be admin-only (``admin.settings``),
must never return a secret unmasked, and must audit each change.
"""

from unittest.mock import AsyncMock, patch

import pytest
from app.models.enums import UserRole
from app.services.audit import AuditEventType

from tests.helpers import headers, make_user

pytestmark = pytest.mark.usefixtures("no_rate_limit")

BASE = "/api/v1/admin/integrations"
ROUTER = "app.routers.integrations"

ROUTES = [
    ("get", "/courtlistener", None),
    ("post", "/courtlistener", {"api_token": "cl-token-0123456789"}),
    ("delete", "/courtlistener", None),
    ("get", "/connectors", None),
    ("post", "/connectors/google", {"values": {"google_client_id": "abc"}}),
    ("delete", "/connectors/google", None),
    ("get", "/local-llm", None),
    ("post", "/local-llm", {"base_url": "http://localhost:11434/v1", "chat_model": "llama3"}),
    ("delete", "/local-llm", None),
]


def _call(client, method, path, body, **kwargs):
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(f"{BASE}{path}", **kwargs)


@pytest.fixture
def admin():
    return make_user("int-admin", UserRole.ADMIN)


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_requires_authentication(client, method, path, body):
    assert _call(client, method, path, body).status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_non_admin_is_forbidden(client, method, path, body):
    """An attorney has every workspace permission but not admin.settings."""
    attorney = make_user("int-attorney", UserRole.ATTORNEY)
    with (
        patch(f"{ROUTER}.set_secret", new_callable=AsyncMock) as set_secret,
        patch(f"{ROUTER}.delete_secret", new_callable=AsyncMock) as delete_secret,
    ):
        resp = _call(client, method, path, body, headers=headers(attorney))
    assert resp.status_code == 403
    set_secret.assert_not_awaited()
    delete_secret.assert_not_awaited()


class TestCourtListener:
    def test_status_masks_the_instance_token(self, client, admin):
        token = "cl-token-0123456789"
        with patch(f"{ROUTER}.get_secret", new_callable=AsyncMock, return_value=token):
            resp = client.get(f"{BASE}/courtlistener", headers=headers(admin))
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True
        assert body["source"] == "instance"
        assert token not in resp.text
        assert body["masked"].startswith("cl-t") and body["masked"].endswith("6789")

    def test_set_stores_applies_and_audits_without_the_token(self, client, admin, audit_events):
        token = "cl-token-0123456789"
        with (
            patch(f"{ROUTER}.set_secret", new_callable=AsyncMock) as set_secret,
            patch(f"{ROUTER}.apply_courtlistener_token") as apply,
        ):
            resp = client.post(
                f"{BASE}/courtlistener", json={"api_token": f"  {token}  "}, headers=headers(admin)
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"
        assert token not in resp.text
        set_secret.assert_awaited_once_with("courtlistener_api_token", token)
        apply.assert_called_once_with(token)

        assert len(audit_events) == 1
        event = audit_events[0]
        assert event["event_type"] == AuditEventType.SETTINGS_CHANGE
        assert event["user_id"] == admin.id
        assert event["details"] == {"action": "courtlistener_token_set"}
        assert token not in str(event)

    def test_short_token_is_rejected(self, client, admin):
        resp = client.post(
            f"{BASE}/courtlistener", json={"api_token": "short"}, headers=headers(admin)
        )
        assert resp.status_code == 422

    def test_clear_deletes_and_audits(self, client, admin, audit_events):
        with (
            patch(f"{ROUTER}.delete_secret", new_callable=AsyncMock) as delete_secret,
            patch(f"{ROUTER}.apply_courtlistener_token"),
        ):
            resp = client.delete(f"{BASE}/courtlistener", headers=headers(admin))
        assert resp.status_code == 200
        assert resp.json() == {"status": "cleared"}
        delete_secret.assert_awaited_once_with("courtlistener_api_token")
        assert [e["details"]["action"] for e in audit_events] == ["courtlistener_token_cleared"]


class TestConnectorCredentials:
    def test_unknown_provider_is_404(self, client, admin):
        resp = client.post(
            f"{BASE}/connectors/not-a-provider",
            json={"values": {"x": "y"}},
            headers=headers(admin),
        )
        assert resp.status_code == 404

    def test_unknown_fields_are_ignored(self, client, admin):
        """Only the provider's own settings fields may be written."""
        with patch(f"{ROUTER}.set_secret", new_callable=AsyncMock) as set_secret:
            resp = client.post(
                f"{BASE}/connectors/google",
                json={"values": {"secret_key": "overwrite-me", "debug": "true"}},
                headers=headers(admin),
            )
        assert resp.status_code == 400
        set_secret.assert_not_awaited()

    def test_oversized_value_is_rejected(self, client, admin):
        resp = client.post(
            f"{BASE}/connectors/google",
            json={"values": {"google_client_id": "x" * 2001}},
            headers=headers(admin),
        )
        assert resp.status_code == 422


class TestLocalLLM:
    def test_set_applies_and_audits(self, client, admin, audit_events):
        with (
            patch(f"{ROUTER}.set_secret", new_callable=AsyncMock),
            patch(f"{ROUTER}.llm_clients.set_runtime") as set_runtime,
        ):
            resp = client.post(
                f"{BASE}/local-llm",
                json={"base_url": "http://localhost:11434/v1", "chat_model": "llama3"},
                headers=headers(admin),
            )
        assert resp.status_code == 200
        assert resp.json()["utility_model"] == "llama3"  # defaults to the chat model
        set_runtime.assert_called_once_with(
            base_url="http://localhost:11434/v1", chat_model="llama3", utility_model="llama3"
        )
        assert [e["details"]["action"] for e in audit_events] == ["local_llm_set"]

    @pytest.mark.parametrize("base_url", ["file:///etc/passwd", "localhost:11434", "ftp://host/v1"])
    def test_non_http_base_url_is_rejected(self, client, admin, base_url):
        with patch(f"{ROUTER}.set_secret", new_callable=AsyncMock) as set_secret:
            resp = client.post(
                f"{BASE}/local-llm",
                json={"base_url": base_url, "chat_model": "llama3"},
                headers=headers(admin),
            )
        assert resp.status_code == 422
        set_secret.assert_not_awaited()
