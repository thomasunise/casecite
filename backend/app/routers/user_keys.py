"""
User API Key Management - Server-Side Storage

This router provides secure server-side storage for user API keys,
replacing the previous approach of sending keys in request headers.

Security Features:
- Keys are encrypted at rest using AES-256-GCM
- Keys are never exposed in responses (only status indicators)
- Keys are scoped per-user
- Audit logging for all key operations
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.models.responses.user_keys import (
    KeyMaskedResponse,
    KeySaveResponse,
)
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData, get_current_user
from app.services.key_storage import (
    get_user_keys,
    save_user_keys,
)
from app.utils.ip_resolution import get_client_ip

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/user/keys", tags=["user-keys"])


# Request/Response Models


class SaveKeyRequest(BaseModel):
    """Request to save an API key."""

    key_type: str  # "openai", "anthropic", "google", "voyage", "cohere"
    api_key: str


class KeyStatusResponse(BaseModel):
    """Response showing which keys are configured (not the actual keys)."""

    openai_configured: bool = False
    anthropic_configured: bool = False
    google_configured: bool = False
    voyage_configured: bool = False
    cohere_configured: bool = False
    last_updated: str | None = None


ALLOWED_KEY_TYPES = ["openai", "anthropic", "google", "voyage", "cohere"]


# Endpoints


@router.post("/save", response_model=KeySaveResponse)
async def save_api_key(
    request: Request,
    body: SaveKeyRequest,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """
    Save an API key for the current user.

    Keys are encrypted at rest and never returned in responses.
    Only the current user can access their own keys.
    """
    if body.key_type not in ALLOWED_KEY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid key type. Allowed: {', '.join(ALLOWED_KEY_TYPES)}",
        )

    # Clean common paste artifacts BEFORE validating: surrounding whitespace
    # and smart punctuation (curly quotes, en/em dashes) that rich-text
    # sources and mobile keyboards substitute. A non-ASCII character in a key
    # crashes header encoding on every later API call with an opaque
    # "'ascii' codec can't encode" error — reject it here with a clear one.
    cleaned_key = body.api_key.strip().strip("\"'“”‘’")
    cleaned_key = cleaned_key.replace("–", "-").replace("—", "-").replace("−", "-")
    if not cleaned_key.isascii():
        bad = ", ".join(sorted({repr(c) for c in cleaned_key if not c.isascii()})[:5])
        raise HTTPException(
            status_code=400,
            detail=f"API key contains invalid characters ({bad}) — usually a "
            "copy-paste artifact. Re-copy the key directly from the provider.",
        )

    # Basic validation
    if not cleaned_key or len(cleaned_key) < 10:
        raise HTTPException(status_code=400, detail="Invalid API key format")

    # Get existing keys and update
    keys = get_user_keys(current_user.user_id)
    keys[body.key_type] = cleaned_key
    keys["_last_updated"] = datetime.now(UTC).isoformat()
    try:
        save_user_keys(current_user.user_id, keys)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Key storage temporarily unavailable")

    # Audit log (don't log the actual key)
    await audit_service.log_event(
        event_type=AuditEventType.SETTINGS_CHANGE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="api_key",
        resource_id=body.key_type,
        ip_address=get_client_ip(request),
        details={"action": "api_key_saved", "key_type": body.key_type},
    )

    return {"status": "saved", "key_type": body.key_type}


@router.get("/status", response_model=KeyStatusResponse)
async def get_key_status(current_user: TokenData = Depends(get_current_user)) -> KeyStatusResponse:
    """
    Get status of configured API keys for the current user.

    Returns only whether each key is configured, not the actual keys.
    """
    keys = get_user_keys(current_user.user_id)

    return KeyStatusResponse(
        openai_configured=bool(keys.get("openai")),
        anthropic_configured=bool(keys.get("anthropic")),
        google_configured=bool(keys.get("google")),
        voyage_configured=bool(keys.get("voyage")),
        cohere_configured=bool(keys.get("cohere")),
        last_updated=keys.get("_last_updated"),
    )


@router.get("/masked", response_model=KeyMaskedResponse)
async def get_masked_keys(current_user: TokenData = Depends(get_current_user)) -> dict:
    """
    Get masked versions of configured API keys for UI display.

    Returns the first few and last few characters of each key so users
    can verify which key is saved without exposing the full secret.
    Example: "sk-••••••••Xs4k"
    """
    keys = get_user_keys(current_user.user_id)
    masked = {}
    for key_type in ALLOWED_KEY_TYPES:
        value = keys.get(key_type)
        if value and len(value) >= 10:
            # Show first 4 and last 4 chars
            masked[key_type] = value[:4] + "\u2022" * 8 + value[-4:]
        else:
            masked[key_type] = None
    return masked
