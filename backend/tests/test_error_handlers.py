"""
Error handler tests — validation failures must not leak request bodies into logs.

`RequestValidationError.__str__` includes pydantic's `input` payload, so
logging `{exc}` would write submitted passwords and BYOK API keys to the
container log stream. The handler logs only field locations and error types.
"""

import logging
from unittest.mock import patch

import pytest
from app.config import settings
from fastapi.testclient import TestClient

FAKE_PASSWORD = "Sup3r-Secret-Passw0rd!"  # gitleaks:allow - fake fixture
FAKE_API_KEY = "sk-leak-canary-1234567890abcdef"  # gitleaks:allow - fake fixture


class TestValidationErrorLogging:
    def test_login_validation_error_does_not_log_password(self, client, caplog):
        with caplog.at_level(logging.WARNING, logger="app.error_handlers"):
            resp = client.post(
                "/api/v1/auth/login",
                json={"password": FAKE_PASSWORD},  # email missing -> 422
            )
        assert resp.status_code == 422
        assert FAKE_PASSWORD not in caplog.text
        assert "Validation error [ERR-" in caplog.text
        assert "email=missing" in caplog.text

    def test_key_save_validation_error_does_not_log_api_key(self, client, auth_headers, caplog):
        with caplog.at_level(logging.WARNING, logger="app.error_handlers"):
            resp = client.post(
                "/api/v1/user/keys/save",
                json={"api_key": FAKE_API_KEY},  # key_type missing -> 422
                headers=auth_headers,
            )
        assert resp.status_code == 422
        assert FAKE_API_KEY not in caplog.text
        assert "key_type=missing" in caplog.text

    def test_validation_error_response_does_not_echo_input(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={"password": FAKE_PASSWORD},
        )
        assert resp.status_code == 422
        assert FAKE_PASSWORD not in resp.text
        assert resp.json()["error_ref"].startswith("ERR-")


SECRET_CANARY = "canary-s3cret-value-from-an-exception-message"  # gitleaks:allow - fake fixture


@pytest.fixture
def quiet_client(app):
    """A client that returns the 500 response instead of re-raising."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestUnhandledExceptions:
    """Exception MESSAGES can carry SQL parameters and document text: they must
    reach neither the audit trail nor (outside DEBUG) the application log."""

    @staticmethod
    def _boom(*_args, **_kwargs):
        raise RuntimeError(SECRET_CANARY)

    def test_message_is_never_copied_into_the_audit_trail(
        self, quiet_client, auth_headers, audit_events
    ):
        with patch("app.routers.auth.session_manager.get_active_sessions", self._boom):
            resp = quiet_client.get("/api/v1/auth/sessions", headers=auth_headers)
        assert resp.status_code == 500
        assert SECRET_CANARY not in str(audit_events)
        failures = [e for e in audit_events if e["event_type"].name == "SUSPICIOUS_ACTIVITY"]
        assert failures, "the failure itself must still be audited"
        assert all(e["details"].get("error_type") == "RuntimeError" for e in failures)

    def test_production_logs_type_and_location_but_not_the_message(
        self, quiet_client, auth_headers, caplog
    ):
        production = settings.model_copy(update={"debug": False})
        with (
            patch("app.error_handlers.settings", production),
            patch("app.routers.auth.session_manager.get_active_sessions", self._boom),
            caplog.at_level(logging.ERROR, logger="app.error_handlers"),
        ):
            resp = quiet_client.get("/api/v1/auth/sessions", headers=auth_headers)
        assert resp.status_code == 500
        assert SECRET_CANARY not in resp.text
        assert resp.json()["error_ref"].startswith("ERR-")
        logged = "\n".join(r.getMessage() for r in caplog.records if r.name == "app.error_handlers")
        assert "RuntimeError" in logged
        assert resp.json()["error_ref"] in logged
        assert "test_error_handlers.py" in logged  # code location is kept
        assert SECRET_CANARY not in logged
        assert all(r.exc_info is None for r in caplog.records if r.name == "app.error_handlers")


class TestDenialAuditing:
    def test_anonymous_401s_are_audited_at_most_once_per_window(self, client, audit_events):
        from app import error_handlers

        error_handlers._anon_401_last_audit.clear()
        for _ in range(5):
            assert client.get("/api/v1/auth/me").status_code == 401
        denials = [e for e in audit_events if e["event_type"].name == "ACCESS_DENIED"]
        assert len(denials) == 1

    def test_requests_presenting_credentials_are_always_audited(self, client, audit_events):
        from app import error_handlers

        error_handlers._anon_401_last_audit.clear()
        bad = {"Authorization": "Bearer not.a.token"}
        for _ in range(3):
            assert client.get("/api/v1/auth/me", headers=bad).status_code == 401
        denials = [e for e in audit_events if e["event_type"].name == "ACCESS_DENIED"]
        assert len(denials) == 3

    def test_403s_are_always_audited(self, client, non_admin_headers, audit_events):
        for _ in range(2):
            resp = client.get("/api/v1/admin/users", headers=non_admin_headers)
            assert resp.status_code == 403
        denials = [e for e in audit_events if e["event_type"].name == "ACCESS_DENIED"]
        assert len(denials) == 2


class TestActionRequiredCode:
    def test_code_is_surfaced_in_the_error_body(self):
        from app.services.auth import AuthActionRequired

        exc = AuthActionRequired("password_change_required", "Change your password.")
        assert exc.status_code == 403
        assert exc.code == "password_change_required"

    def test_ordinary_errors_carry_no_code(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        assert "code" not in resp.json()
