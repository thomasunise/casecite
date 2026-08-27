"""
User API Keys - BYOK (Bring Your Own Key) Support

Extracts user-provided API keys from request headers and creates
on-demand clients for OpenAI, Anthropic, Google, etc.

When a user_id is provided, falls back to server-side encrypted storage
for any key not found in request headers (transition from header-based BYOK).
"""

import logging
from dataclasses import dataclass

from anthropic import Anthropic, AsyncAnthropic
from fastapi import Depends, Request
from openai import AsyncOpenAI, OpenAI

from app.config import settings
from app.services.auth import TokenData, get_current_user

logger = logging.getLogger(__name__)


def _clean_key(value: str | None) -> str | None:
    """Repair paste artifacts in an API key; drop it if still non-ASCII.

    A key with smart quotes / unicode dashes (rich-text copy-paste, mobile
    autocorrect) crashes HTTP header encoding on EVERY later API call with an
    opaque "'ascii' codec can't encode" error. Repair the common substitutions;
    a key that still isn't ASCII is unusable — treat it as absent so the user
    gets a clear "configure your API key" message instead of a codec crash.
    """
    if not value:
        return None
    cleaned = value.strip().strip("\"'“”‘’")
    cleaned = cleaned.replace("–", "-").replace("—", "-").replace("−", "-")
    if not cleaned:
        return None
    if not cleaned.isascii():
        logger.warning("Discarding stored API key with non-ASCII characters (paste artifact)")
        return None
    return cleaned


@dataclass
class UserAPIKeys:
    """Container for user-provided API keys."""

    openai: str | None = None
    anthropic: str | None = None
    google: str | None = None
    voyage: str | None = None
    cohere: str | None = None

    @classmethod
    def from_request(cls, request: Request, user_id: str | None = None) -> "UserAPIKeys":
        """Extract API keys from request headers, with server-side fallback.

        When user_id is provided, any key not found in headers will be
        looked up from server-side encrypted storage. Headers take precedence.
        """
        keys = cls(
            openai=request.headers.get("X-OpenAI-Key"),
            anthropic=request.headers.get("X-Anthropic-Key"),
            google=request.headers.get("X-Google-Key"),
            voyage=request.headers.get("X-Voyage-Key"),
            cohere=request.headers.get("X-Cohere-Key"),
        )

        # Fall back to server-stored keys for any missing key
        if user_id:
            try:
                from app.services.key_storage import get_user_api_key

                if not keys.openai:
                    keys.openai = _clean_key(get_user_api_key(user_id, "openai"))
                if not keys.anthropic:
                    keys.anthropic = _clean_key(get_user_api_key(user_id, "anthropic"))
                if not keys.google:
                    keys.google = _clean_key(get_user_api_key(user_id, "google"))
                if not keys.voyage:
                    keys.voyage = _clean_key(get_user_api_key(user_id, "voyage"))
                if not keys.cohere:
                    keys.cohere = _clean_key(get_user_api_key(user_id, "cohere"))
            except (ImportError, AttributeError, KeyError, ValueError, OSError):
                logger.debug("Could not load server-stored keys for user %s", user_id)

        return keys

    @classmethod
    def for_user(cls, user_id: str) -> "UserAPIKeys":
        """Load a user's server-stored keys without a request context.

        For background work (e.g. startup re-indexing) acting on behalf of a
        user when no HTTP request exists. Stored keys were validated at save.
        """
        keys = cls()
        try:
            from app.services.key_storage import get_user_api_key

            keys.openai = _clean_key(get_user_api_key(user_id, "openai"))
            keys.anthropic = _clean_key(get_user_api_key(user_id, "anthropic"))
            keys.google = _clean_key(get_user_api_key(user_id, "google"))
            keys.voyage = _clean_key(get_user_api_key(user_id, "voyage"))
            keys.cohere = _clean_key(get_user_api_key(user_id, "cohere"))
        except (ImportError, AttributeError, KeyError, ValueError, OSError):
            logger.debug("Could not load server-stored keys for user %s", user_id)
        return keys

    @staticmethod
    def _validate_key_format(key: str | None, provider: str) -> str | None:
        """Validate API key format. Returns the key if valid, None otherwise."""
        if not key:
            return None
        key = key.strip()
        if len(key) < 10 or len(key) > 256:
            logger.warning("Invalid %s key length: %d", provider, len(key))
            return None
        # Provider-specific prefix checks
        prefix_checks = {
            "openai": ("sk-",),
            "anthropic": ("sk-ant-",),
            "voyage": ("pa-", "vo-"),
        }
        prefixes = prefix_checks.get(provider)
        if prefixes and not any(key.startswith(p) for p in prefixes):
            logger.warning("Invalid %s key prefix", provider)
            return None
        return key

    def __post_init__(self):
        """Repair paste artifacts, then validate key formats on creation."""
        self.openai = _clean_key(self.openai)
        self.anthropic = _clean_key(self.anthropic)
        self.google = _clean_key(self.google)
        self.voyage = _clean_key(self.voyage)
        self.cohere = _clean_key(self.cohere)
        self.openai = self._validate_key_format(self.openai, "openai")
        self.anthropic = self._validate_key_format(self.anthropic, "anthropic")
        self.voyage = self._validate_key_format(self.voyage, "voyage")
        # Google and Cohere keys don't have consistent prefixes
        if self.google and (len(self.google.strip()) < 10 or len(self.google.strip()) > 256):
            self.google = None
        if self.cohere and (len(self.cohere.strip()) < 10 or len(self.cohere.strip()) > 256):
            self.cohere = None

    def has_openai(self) -> bool:
        return bool(self.openai)

    def has_anthropic(self) -> bool:
        return bool(self.anthropic)

    def has_google(self) -> bool:
        return bool(self.google)

    def has_voyage(self) -> bool:
        return bool(self.voyage)

    def has_cohere(self) -> bool:
        return bool(self.cohere)

    def get_openai_client(self) -> OpenAI | None:
        """Create sync OpenAI client with the user key, or the instance endpoint."""
        from app.services.llm_clients import is_custom_endpoint, make_openai

        if self.openai or is_custom_endpoint():
            return make_openai(self.openai, async_=False)
        return None

    def get_async_openai_client(self) -> AsyncOpenAI | None:
        """Create async OpenAI client with the user key, or the instance endpoint."""
        from app.services.llm_clients import is_custom_endpoint, make_openai

        if self.openai or is_custom_endpoint():
            return make_openai(self.openai, async_=True)
        return None

    def get_anthropic_client(self) -> Anthropic | None:
        """Create sync Anthropic client with user key (timeout + bounded retries)."""
        if self.anthropic:
            return Anthropic(api_key=self.anthropic, timeout=settings.api_timeout, max_retries=2)
        return None

    def get_async_anthropic_client(self) -> AsyncAnthropic | None:
        """Create async Anthropic client with user key (for RAG pipeline)."""
        if self.anthropic:
            return AsyncAnthropic(
                api_key=self.anthropic, timeout=settings.api_timeout, max_retries=2
            )
        return None

    def get_google_model(self, model_name: str = "gemini-3.1-pro-preview"):
        """Create Google Generative AI model with user key.

        Returns an adapter over the new-SDK ``genai.Client`` or a per-key
        ``GenerativeModel``-shaped REST wrapper — both expose the same
        ``generate_content`` interface — so that each request uses its own API
        key with no global-state leakage between concurrent users.
        """
        if not self.google:
            return None

        # Prefer the new google-genai SDK which supports per-client API keys
        try:
            from google import genai  # google-genai >= 0.4

            # google-genai takes its timeout in milliseconds via http_options.
            client = genai.Client(
                api_key=self.google,
                http_options={"timeout": int(settings.api_timeout * 1000)},
            )
            return _GenAIModelAdapter(client, model_name)
        except (ImportError, TypeError, AttributeError):
            pass

        # Fallback: legacy google-generativeai SDK — use the REST transport
        # directly via httpx to avoid the process-global configure() call.
        try:
            return _IsolatedGeminiModel(api_key=self.google, model_name=model_name)
        except (ValueError, TypeError, AttributeError):
            return None


class _GenAIModelAdapter:
    """Adapt the new google-genai ``Client`` to the legacy ``generate_content``
    interface the RAG pipeline calls (``response.text`` works on both SDKs)."""

    def __init__(self, client, model_name: str):
        self._client = client
        self._model_name = model_name

    def generate_content(self, prompt: str | list, **kwargs):
        contents = prompt if isinstance(prompt, str) else str(prompt)
        return self._client.models.generate_content(model=self._model_name, contents=contents)


class _IsolatedGeminiModel:
    """Thin REST wrapper for Gemini that avoids the global ``genai.configure()`` call.

    Provides a ``generate_content`` interface compatible with the legacy
    ``google.generativeai.GenerativeModel`` so callers don't need to change.
    """

    _BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model_name: str = "gemini-3.1-pro-preview"):
        self._api_key = api_key
        self._model_name = model_name

    def generate_content(self, prompt: str | list, **kwargs):
        """Synchronous content generation via REST (no global state)."""
        import httpx

        contents = [{"parts": [{"text": prompt if isinstance(prompt, str) else str(prompt)}]}]
        url = f"{self._BASE}/{self._model_name}:generateContent"
        resp = httpx.post(
            url,
            json={"contents": contents},
            headers={"x-goog-api-key": self._api_key},
            timeout=settings.api_timeout,
        )
        resp.raise_for_status()
        return resp.json()

    async def generate_content_async(self, prompt: str | list, **kwargs):
        """Async content generation via REST (no global state)."""
        import httpx

        contents = [{"parts": [{"text": prompt if isinstance(prompt, str) else str(prompt)}]}]
        url = f"{self._BASE}/{self._model_name}:generateContent"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                json={"contents": contents},
                headers={"x-goog-api-key": self._api_key},
            )
        resp.raise_for_status()
        return resp.json()


def get_user_keys(
    request: Request,
    current_user: TokenData = Depends(get_current_user),
) -> UserAPIKeys:
    """FastAPI dependency to get user API keys from request with server-side fallback."""
    return UserAPIKeys.from_request(request, user_id=current_user.user_id)
