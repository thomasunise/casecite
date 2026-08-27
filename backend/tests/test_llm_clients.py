"""
Tests for the central OpenAI client factory (app/services/llm_clients.py).

Every client the app builds must carry a request timeout and bounded retries so
a hung upstream can never pin a request (or a worker thread) forever.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import patch

from app.config import settings
from app.services.llm_clients import SDK_MAX_RETRIES, make_openai


class TestMakeOpenAI:
    def test_sync_client_carries_timeout_and_bounded_retries(self):
        with patch.dict("app.services.llm_clients._runtime", {"base_url": None}):
            client = make_openai("sk-test-ci-dummy-key-not-real", async_=False)
        assert client.timeout == settings.api_timeout
        assert client.max_retries == SDK_MAX_RETRIES == 2

    def test_async_client_carries_timeout_and_bounded_retries(self):
        with patch.dict("app.services.llm_clients._runtime", {"base_url": None}):
            client = make_openai("sk-test-ci-dummy-key-not-real", async_=True)
        assert client.timeout == settings.api_timeout
        assert client.max_retries == 2

    def test_timeout_override_is_honored(self):
        with patch.dict("app.services.llm_clients._runtime", {"base_url": None}):
            client = make_openai("sk-test-ci-dummy-key-not-real", timeout=120.0, max_retries=0)
        assert client.timeout == 120.0
        assert client.max_retries == 0

    def test_custom_endpoint_keeps_bounds(self):
        with patch.dict(
            "app.services.llm_clients._runtime", {"base_url": "http://localhost:11434/v1"}
        ):
            client = make_openai(None, async_=True)
        assert str(client.base_url).startswith("http://localhost:11434/v1")
        assert client.timeout == settings.api_timeout
        assert client.max_retries == 2

    def test_no_key_and_no_endpoint_returns_none(self):
        with (
            patch.dict("app.services.llm_clients._runtime", {"base_url": None}),
            patch("app.services.llm_clients.settings") as mock_settings,
        ):
            mock_settings.openai_api_key = None
            assert make_openai(None) is None
