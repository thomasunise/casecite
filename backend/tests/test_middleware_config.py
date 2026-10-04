"""TrustedHost / CORS configuration (app/middleware/middleware_config.py).

Regression: the production compose files set ALLOWED_HOSTS to the public
hostname only, while every container healthcheck probes http://localhost — so
the probe got a 400 and the container never became healthy.
"""

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars")
os.environ.setdefault("DEBUG", "true")

from app.middleware import middleware_config  # noqa: E402


def _configure(env: dict[str, str], debug: bool = False) -> FastAPI:
    """Run configure_middleware against a bare app under the given environment."""
    app = FastAPI()
    cleared = {k: "" for k in ("ALLOWED_HOSTS", "CORS_ORIGINS", "FORCE_HTTPS", "TRUSTED_PROXIES")}
    with (
        patch.dict(os.environ, {**cleared, **env}),
        patch.object(middleware_config, "settings") as settings,
    ):
        settings.debug = debug
        middleware_config.configure_middleware(app)
    return app


def _allowed_hosts(app: FastAPI) -> list[str]:
    for middleware in app.user_middleware:
        if middleware.cls is TrustedHostMiddleware:
            return list(middleware.kwargs["allowed_hosts"])
    raise AssertionError("TrustedHostMiddleware is not registered")


class TestAllowedHosts:
    def test_loopback_is_allowed_alongside_the_public_hostname(self):
        app = _configure(
            {"ALLOWED_HOSTS": "app.example.com", "CORS_ORIGINS": "https://app.example.com"}
        )
        hosts = _allowed_hosts(app)
        assert hosts[0] == "app.example.com"
        assert "localhost" in hosts
        assert "127.0.0.1" in hosts

    def test_other_hosts_are_still_rejected(self):
        app = _configure(
            {"ALLOWED_HOSTS": "app.example.com", "CORS_ORIGINS": "https://app.example.com"}
        )
        hosts = _allowed_hosts(app)
        assert "*" not in hosts
        assert "evil.example.net" not in hosts

    def test_loopback_is_not_duplicated(self):
        app = _configure(
            {
                "ALLOWED_HOSTS": "localhost, app.example.com",
                "CORS_ORIGINS": "https://app.example.com",
            }
        )
        hosts = _allowed_hosts(app)
        assert hosts.count("localhost") == 1

    def test_unset_in_production_is_loopback_only(self):
        app = _configure({"CORS_ORIGINS": "https://app.example.com"})
        assert _allowed_hosts(app) == ["localhost", "127.0.0.1"]


class TestCorsLocalhost:
    def test_localhost_origin_rejected_for_a_public_instance(self):
        with pytest.raises(ValueError, match="Localhost origins not allowed"):
            _configure({"ALLOWED_HOSTS": "app.example.com", "CORS_ORIGINS": "https://localhost"})

    def test_localhost_origin_accepted_for_the_localhost_trial(self):
        # DOMAIN=localhost with docker-compose.prod.yml: both values derive from it.
        app = _configure({"ALLOWED_HOSTS": "localhost", "CORS_ORIGINS": "https://localhost"})
        assert _allowed_hosts(app) == ["localhost", "127.0.0.1"]

    def test_missing_cors_origins_still_refuses_to_start(self):
        with pytest.raises(ValueError, match="CORS_ORIGINS must be set"):
            _configure({"ALLOWED_HOSTS": "app.example.com"})
