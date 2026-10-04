"""
Unit tests for the UserKeys service (BYOK support).
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import MagicMock, patch

from app.config import settings
from app.services.user_keys import UserAPIKeys, _IsolatedGeminiModel


def _make_mock_request(headers=None):
    """Create a mock FastAPI Request with given headers."""
    mock_request = MagicMock()
    mock_request.headers = headers or {}
    return mock_request


# =============================================================================
# UserAPIKeys Initialization / Validation Tests
# =============================================================================


class TestUserAPIKeysValidation:
    """Tests for UserAPIKeys key validation."""

    def test_valid_openai_key(self):
        keys = UserAPIKeys(openai="sk-" + "a" * 48)
        assert keys.openai is not None
        assert keys.openai

    def test_openai_compatible_gateway_key_is_accepted(self):
        """The OpenAI slot also carries gateway keys (Groq "gsk_", OpenRouter
        "sk-or-", Together) — a missing "sk-" prefix must not discard them."""
        keys = UserAPIKeys(openai="gsk_" + "a" * 48)
        assert keys.openai == "gsk_" + "a" * 48

    def test_placeholder_keys_are_treated_as_absent(self):
        keys = UserAPIKeys(
            openai="sk-your-openai-api-key",
            anthropic="sk-ant-your-anthropic-key",
            voyage="pa-your-voyage-key",
            google="your-google-api-key",
        )
        assert keys.openai is None
        assert keys.anthropic is None
        assert keys.voyage is None

    def test_invalid_openai_key_too_short(self):
        keys = UserAPIKeys(openai="sk-abc")
        assert keys.openai is None

    def test_invalid_openai_key_too_long(self):
        keys = UserAPIKeys(openai="sk-" + "a" * 300)
        assert keys.openai is None

    def test_valid_anthropic_key(self):
        keys = UserAPIKeys(anthropic="sk-ant-" + "b" * 48)
        assert keys.anthropic is not None
        assert keys.anthropic

    def test_invalid_anthropic_key_wrong_prefix(self):
        keys = UserAPIKeys(anthropic="invalid-" + "b" * 48)
        assert keys.anthropic is None

    def test_valid_voyage_key_pa_prefix(self):
        keys = UserAPIKeys(voyage="pa-" + "c" * 48)
        assert keys.voyage is not None
        assert keys.voyage

    def test_valid_voyage_key_vo_prefix(self):
        keys = UserAPIKeys(voyage="vo-" + "c" * 48)
        assert keys.voyage is not None

    def test_invalid_voyage_key(self):
        keys = UserAPIKeys(voyage="wrong-" + "c" * 48)
        assert keys.voyage is None

    def test_google_key_length_validation(self):
        keys = UserAPIKeys(google="a" * 40)
        assert keys.google is not None
        assert keys.google

    def test_google_key_too_short(self):
        keys = UserAPIKeys(google="abc")
        assert keys.google is None
        assert not keys.google

    def test_google_key_too_long(self):
        keys = UserAPIKeys(google="a" * 300)
        assert keys.google is None

    def test_cohere_key_length_validation(self):
        keys = UserAPIKeys(cohere="x" * 40)
        assert keys.cohere is not None
        assert keys.cohere

    def test_cohere_key_too_short(self):
        keys = UserAPIKeys(cohere="x" * 5)
        assert keys.cohere is None

    def test_none_keys_stay_none(self):
        keys = UserAPIKeys()
        assert keys.openai is None
        assert keys.anthropic is None
        assert keys.google is None
        assert keys.voyage is None
        assert keys.cohere is None

    def test_whitespace_stripped(self):
        keys = UserAPIKeys(openai="  sk-" + "a" * 48 + "  ")
        assert keys.openai is not None
        assert not keys.openai.startswith(" ")


# =============================================================================
# from_request Tests
# =============================================================================


class TestFromRequest:
    """Tests for UserAPIKeys.from_request."""

    def test_extracts_headers(self):
        request = _make_mock_request(
            {
                "X-OpenAI-Key": "sk-" + "a" * 48,
                "X-Anthropic-Key": "sk-ant-" + "b" * 48,
            }
        )

        keys = UserAPIKeys.from_request(request)
        assert keys.openai
        assert keys.anthropic

    def test_missing_headers_return_none(self):
        request = _make_mock_request({})

        keys = UserAPIKeys.from_request(request)
        assert keys.openai is None
        assert keys.anthropic is None

    def test_server_side_fallback_with_user_id(self):
        request = _make_mock_request({})  # No headers

        with patch("app.services.key_storage.get_user_api_key") as mock_get_key:
            mock_get_key.side_effect = lambda uid, key_type: {
                "openai": "sk-" + "z" * 48,
            }.get(key_type)

            keys = UserAPIKeys.from_request(request, user_id="user-1")
            assert keys.openai

    def test_headers_take_precedence_over_stored(self):
        request = _make_mock_request({"X-OpenAI-Key": "sk-" + "a" * 48})

        with patch("app.services.key_storage.get_user_api_key") as mock_get_key:
            # Stored key should not be used since header is present
            mock_get_key.return_value = "sk-" + "b" * 48

            keys = UserAPIKeys.from_request(request, user_id="user-1")
            assert keys.openai == "sk-" + "a" * 48

    def test_graceful_when_key_storage_unavailable(self):
        request = _make_mock_request({})

        with patch(
            "app.services.key_storage.get_user_api_key",
            side_effect=ValueError("storage broken"),
        ):
            # Should not raise -- from_request catches various exceptions
            keys = UserAPIKeys.from_request(request, user_id="user-1")
            assert keys.openai is None


# =============================================================================
# Client Creation Tests
# =============================================================================


class TestClientCreation:
    """Tests for API client creation methods."""

    def test_get_openai_client_with_key(self):
        keys = UserAPIKeys(openai="sk-" + "a" * 48)

        # Client creation is delegated to the llm_clients factory so the whole
        # app can honor a custom (self-hosted) endpoint. With no custom
        # base_url configured, the user's key is passed straight through.
        with (
            patch.dict("app.services.llm_clients._runtime", {"base_url": None}),
            patch("app.services.llm_clients.OpenAI") as mock_openai,
        ):
            _client = keys.get_openai_client()
            mock_openai.assert_called_once_with(
                api_key=keys.openai, timeout=settings.api_timeout, max_retries=2
            )

    def test_get_openai_client_without_key(self):
        keys = UserAPIKeys()
        assert keys.get_openai_client() is None

    def test_get_async_openai_client_with_key(self):
        keys = UserAPIKeys(openai="sk-" + "a" * 48)

        with (
            patch.dict("app.services.llm_clients._runtime", {"base_url": None}),
            patch("app.services.llm_clients.AsyncOpenAI") as mock_async_openai,
        ):
            _client = keys.get_async_openai_client()
            mock_async_openai.assert_called_once_with(
                api_key=keys.openai, timeout=settings.api_timeout, max_retries=2
            )

    def test_get_async_openai_client_without_key(self):
        keys = UserAPIKeys()
        assert keys.get_async_openai_client() is None

    def test_get_anthropic_client_with_key(self):
        keys = UserAPIKeys(anthropic="sk-ant-" + "b" * 48)

        with patch("app.services.user_keys.Anthropic") as mock_anthropic:
            _client = keys.get_anthropic_client()
            mock_anthropic.assert_called_once_with(
                api_key=keys.anthropic, timeout=settings.api_timeout, max_retries=2
            )

    def test_get_anthropic_client_without_key(self):
        keys = UserAPIKeys()
        assert keys.get_anthropic_client() is None

    def test_get_async_anthropic_client_with_key(self):
        keys = UserAPIKeys(anthropic="sk-ant-" + "b" * 48)

        with patch("app.services.user_keys.AsyncAnthropic") as mock_async_anthropic:
            _client = keys.get_async_anthropic_client()
            mock_async_anthropic.assert_called_once_with(
                api_key=keys.anthropic, timeout=settings.api_timeout, max_retries=2
            )

    def test_real_openai_clients_carry_timeout_and_bounded_retries(self):
        """The constructed SDK clients (no mocks) expose the configured bounds."""
        keys = UserAPIKeys(openai="sk-" + "a" * 48)
        with patch.dict("app.services.llm_clients._runtime", {"base_url": None}):
            for client in (keys.get_openai_client(), keys.get_async_openai_client()):
                assert client.timeout == settings.api_timeout
                assert client.max_retries == 2

    def test_get_google_model_without_key(self):
        keys = UserAPIKeys()
        assert keys.get_google_model() is None

    def test_get_google_model_uses_the_selected_model(self):
        """Regression: the user's Gemini choice was ignored for a fixed default."""
        keys = UserAPIKeys(google="a" * 40)
        fake_genai = MagicMock()
        fake_google = MagicMock(genai=fake_genai)

        with patch.dict("sys.modules", {"google": fake_google, "google.genai": fake_genai}):
            model = keys.get_google_model("gemini-2.5-flash")
            model.generate_content("hello")

        call = fake_genai.Client.return_value.models.generate_content.call_args
        assert call.kwargs["model"] == "gemini-2.5-flash"

    def test_get_google_model_with_key_genai(self):
        keys = UserAPIKeys(google="a" * 40)

        with (
            patch.dict("sys.modules", {"google": MagicMock(), "google.genai": MagicMock()}),
            patch("app.services.user_keys.UserAPIKeys.get_google_model") as mock_method,
        ):
            mock_method.return_value = MagicMock()
            result = keys.get_google_model()
            assert result is not None


# =============================================================================
# _IsolatedGeminiModel Tests
# =============================================================================


class TestIsolatedGeminiModel:
    """Tests for _IsolatedGeminiModel."""

    def test_initialization(self):
        model = _IsolatedGeminiModel(api_key="test-key", model_name="gemini-1.5-pro")
        assert model._api_key == "test-key"
        assert model._model_name == "gemini-1.5-pro"

    def test_generate_content_calls_api(self):
        model = _IsolatedGeminiModel(api_key="test-key")

        with patch("httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {"candidates": []}
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            _result = model.generate_content("Hello, world!")
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            # API key travels in the x-goog-api-key header, never the URL (URLs
            # leak into proxy/exception logs).
            assert "test-key" not in call_args[0][0]
            assert call_args.kwargs["headers"]["x-goog-api-key"] == "test-key"

    def test_generate_content_returns_text_like_the_sdk(self):
        """The REST fallback must expose ``.text`` — the RAG pipeline reads it."""
        model = _IsolatedGeminiModel(api_key="test-key")

        with patch("httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "candidates": [{"content": {"parts": [{"text": "Hello "}, {"text": "there"}]}}]
            }
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            assert model.generate_content("Hi").text == "Hello there"

    def test_default_model_comes_from_settings(self):
        from app.config import settings

        assert _IsolatedGeminiModel(api_key="test-key")._model_name == settings.gemini_model


# =============================================================================
# _validate_key_format Tests
# =============================================================================


class TestValidateKeyFormat:
    """Tests for _validate_key_format static method."""

    def test_none_key_returns_none(self):
        result = UserAPIKeys._validate_key_format(None, "openai")
        assert result is None

    def test_empty_key_returns_none(self):
        result = UserAPIKeys._validate_key_format("", "openai")
        assert result is None

    def test_valid_key_returned(self):
        key = "sk-" + "a" * 48
        result = UserAPIKeys._validate_key_format(key, "openai")
        assert result == key

    def test_provider_without_prefix_check(self):
        # "google" has no prefix check
        key = "AIza" + "x" * 36
        result = UserAPIKeys._validate_key_format(key, "google")
        assert result == key
