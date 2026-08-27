"""
Error handler tests — validation failures must not leak request bodies into logs.

`RequestValidationError.__str__` includes pydantic's `input` payload, so
logging `{exc}` would write submitted passwords and BYOK API keys to the
container log stream. The handler logs only field locations and error types.
"""

import logging

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
