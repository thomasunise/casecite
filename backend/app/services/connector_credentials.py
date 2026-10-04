"""Instance-wide connector (file picker) credentials.

Two ways to configure the Google Drive / OneDrive+SharePoint / Box / Dropbox
pickers, both first-class:

  1. .env variables (open-source self-install) — the fallback.
  2. The admin Settings UI (desktop / private installs where env vars aren't
     practical) — stored AES-256-GCM encrypted via instance settings and
     applied to the RUNNING config immediately, no restart.

Resolution order: instance value (DB) -> .env -> unconfigured. The effective
value lives in a small in-memory holder seeded from .env at import and refreshed
from encrypted instance storage at startup (the `settings` object is frozen and
cannot be mutated at runtime). Every consumer (pickers router, connector
services, system status) reads its fields through :func:`get`.
"""

from __future__ import annotations

import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Provider -> the settings fields it needs. `secret` fields are always fully
# masked in status responses; the rest are partially masked.
CONNECTOR_PROVIDERS: dict[str, dict] = {
    "google": {
        "label": "Google Drive",
        "fields": ["google_client_id", "google_client_secret", "google_api_key", "google_app_id"],
        "secret_fields": {"google_client_secret", "google_api_key"},
    },
    "microsoft": {
        "label": "OneDrive & SharePoint",
        "fields": ["microsoft_client_id", "microsoft_client_secret", "microsoft_tenant_id"],
        "secret_fields": {"microsoft_client_secret"},
    },
    "box": {
        "label": "Box",
        "fields": ["box_client_id", "box_client_secret"],
        "secret_fields": {"box_client_secret"},
    },
    "dropbox": {
        "label": "Dropbox",
        "fields": ["dropbox_app_key", "dropbox_app_secret"],
        "secret_fields": {"dropbox_app_secret"},
    },
}

_SECRET_PREFIX = "connector_credentials_"

# Snapshot of the .env values, captured before any DB override is applied —
# clearing an instance override reverts to these.
_ENV_DEFAULTS: dict[str, str | None] = {
    field: getattr(settings, field, None)
    for meta in CONNECTOR_PROVIDERS.values()
    for field in meta["fields"]
}

# Effective, runtime-mutable values. Seeded from .env; instance overrides (DB)
# are layered on at startup / when saved via the admin UI. `settings` is frozen,
# so this dict — not the settings object — is the source of truth for consumers.
_runtime: dict[str, str | None] = dict(_ENV_DEFAULTS)


def get(field: str) -> str | None:
    """Live effective value for a connector settings-field (override or .env)."""
    return _runtime.get(field)


def secret_name(provider: str) -> str:
    return f"{_SECRET_PREFIX}{provider}"


def apply_values(provider: str, values: dict[str, str | None]) -> None:
    """Write credential values into the live runtime config for a provider."""
    for field in CONNECTOR_PROVIDERS[provider]["fields"]:
        value = (values.get(field) or "").strip() if values.get(field) else None
        _runtime[field] = value or None


def revert_to_env(provider: str) -> None:
    """Restore a provider's fields to their original .env values."""
    for field in CONNECTOR_PROVIDERS[provider]["fields"]:
        _runtime[field] = _ENV_DEFAULTS.get(field)


def env_configured(provider: str) -> bool:
    """Whether the .env alone configures this provider (first field is the id)."""
    first = CONNECTOR_PROVIDERS[provider]["fields"][0]
    return bool(_ENV_DEFAULTS.get(first))


async def load_all() -> None:
    """Apply every stored instance override at startup (DB beats .env)."""
    from app.services.instance_settings import get_secret

    for provider in CONNECTOR_PROVIDERS:
        try:
            raw = await get_secret(secret_name(provider))
            if not raw:
                continue
            values = json.loads(raw)
            if isinstance(values, dict):
                apply_values(provider, values)
                logger.info("Applied instance connector credentials for %s", provider)
        except Exception as e:  # one bad secret must not break startup
            logger.warning("Failed to load connector credentials for %s: %s", provider, e)


def mask(value: str | None, *, full: bool) -> str | None:
    if not value:
        return None
    if full or len(value) < 10:
        return "•" * 8
    return value[:4] + "•" * 8 + value[-4:]


async def provider_status(provider: str) -> dict:
    """Configured / source / masked values for one provider."""
    from app.services.instance_settings import get_secret

    meta = CONNECTOR_PROVIDERS[provider]
    raw = await get_secret(secret_name(provider))
    instance_values: dict | None = None
    if raw:
        try:
            parsed = json.loads(raw)
            instance_values = parsed if isinstance(parsed, dict) else None
        except (ValueError, TypeError):
            instance_values = None

    if instance_values and any((instance_values.get(f) or "").strip() for f in meta["fields"]):
        source = "instance"
        effective = instance_values
    elif env_configured(provider):
        source = "env"
        effective = {f: _ENV_DEFAULTS.get(f) for f in meta["fields"]}
    else:
        source = "none"
        effective = {}

    return {
        "provider": provider,
        "label": meta["label"],
        "configured": source != "none",
        "source": source,
        "fields": meta["fields"],
        "masked": {
            f: mask(effective.get(f), full=f in meta["secret_fields"]) for f in meta["fields"]
        },
    }
