"""AI provider allowlist — one enforcement point for every outbound AI call.

When ``HIPAA_ENFORCEMENT_ENABLED`` is on, document text and prompts may only be
sent to providers named in ``APPROVED_AI_PROVIDERS``. The check keys on the
client that will actually carry the request (its endpoint), never on the model
name: a model called "gpt-…" served from a custom ``OPENAI_BASE_URL`` is that
endpoint's host, not "openai".

Provider names:

- ``openai``      api.openai.com
- ``anthropic``   Anthropic API
- ``google``      Gemini API
- ``voyage``      Voyage AI embeddings
- ``cohere``      Cohere embeddings
- ``self_hosted`` (alias ``local``) an OpenAI-compatible endpoint on loopback,
  a private address, or a single-label internal hostname
- any other OpenAI-compatible endpoint is identified by its hostname
  (e.g. ``api.groq.com``) and must be listed by that hostname.

This module depends only on settings so every client factory can import it.
"""

import ipaddress
import logging
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger(__name__)

OPENAI_HOST = "api.openai.com"
SELF_HOSTED = "self_hosted"
_SELF_HOSTED_ALIASES = {"self_hosted", "self-hosted", "selfhosted", "local"}


class ProviderNotAllowedError(ValueError):
    """The provider that would receive this call is not on the allowlist."""


def _is_internal_host(host: str) -> bool:
    """Loopback / private address, or a single-label (intranet) hostname."""
    if host in ("localhost", "host.docker.internal"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host
    return ip.is_loopback or ip.is_private or ip.is_link_local


def provider_for_base_url(base_url: str | None) -> str:
    """Provider name for an OpenAI-compatible endpoint URL."""
    host = (urlparse(str(base_url or "")).hostname or "").lower()
    if not host or host == OPENAI_HOST:
        return "openai"
    if _is_internal_host(host):
        return SELF_HOSTED
    return host


def openai_client_provider(client) -> str:
    """Provider behind an OpenAI SDK client, read from the client's endpoint."""
    return provider_for_base_url(getattr(client, "base_url", None))


def enforce_provider_allowed(provider: str, purpose: str = "AI call") -> None:
    """Raise ProviderNotAllowedError unless ``provider`` is approved.

    A no-op while enforcement is disabled (the default).
    """
    if not settings.hipaa_enforcement_enabled:
        return
    approved = {p.strip().lower() for p in settings.approved_ai_providers if p and p.strip()}
    if not approved:
        raise ProviderNotAllowedError(
            "The AI provider allowlist is enabled (HIPAA_ENFORCEMENT_ENABLED) but "
            "APPROVED_AI_PROVIDERS is empty, so no AI call is permitted. Set "
            "APPROVED_AI_PROVIDERS to the providers this instance may use."
        )
    name = (provider or "unknown").lower()
    if name in approved:
        return
    if name == SELF_HOSTED and approved & _SELF_HOSTED_ALIASES:
        return
    logger.warning("Blocked %s: provider '%s' is not on the allowlist", purpose, name)
    raise ProviderNotAllowedError(
        f"This instance restricts AI providers, and '{name}' is not approved for "
        f"this {purpose}. Approved providers: {', '.join(sorted(approved))}. "
        "Choose an approved model in Settings or ask your administrator."
    )


def enforce_openai_client(client, purpose: str = "AI call") -> None:
    """Allowlist check for a call about to go out on an OpenAI SDK client."""
    enforce_provider_allowed(openai_client_provider(client), purpose)
