"""
Admin integrations router.

Instance-wide integration credentials (currently the CourtListener / Free Law
Project API token) editable from the UI instead of only via .env. Admin-only.
The token is persisted AES-256-GCM encrypted and applied to the running service
immediately (no restart). Resolution order: instance token (DB) -> .env -> anonymous.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.services import connector_credentials, llm_clients
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData
from app.services.courtlistener import apply_courtlistener_token
from app.services.instance_settings import delete_secret, get_secret, set_secret
from app.services.permissions import require_permission
from app.utils.ip_resolution import get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/integrations", tags=["admin-integrations"])

CL_SECRET = "courtlistener_api_token"


class CourtListenerTokenRequest(BaseModel):
    api_token: str = Field(..., min_length=10, max_length=200)


def _mask(token: str | None) -> str | None:
    if not token:
        return None
    if len(token) < 10:
        return "•" * 8
    return token[:4] + "•" * 8 + token[-4:]


@router.get("/courtlistener")
async def courtlistener_status(current_user: TokenData = require_permission("admin.settings")):
    """Report whether a CourtListener token is configured, and where it comes from."""
    instance_token = await get_secret(CL_SECRET)
    env_token = (settings.courtlistener_api_token or "").strip() or None
    if instance_token:
        return {"configured": True, "source": "instance", "masked": _mask(instance_token)}
    if env_token:
        return {"configured": True, "source": "env", "masked": _mask(env_token)}
    return {"configured": False, "source": "none", "masked": None}


@router.post("/courtlistener")
async def set_courtlistener_token(
    body: CourtListenerTokenRequest,
    request: Request,
    current_user: TokenData = require_permission("admin.settings"),
):
    """Save an instance-wide CourtListener token and apply it immediately."""
    token = body.api_token.strip()
    await set_secret(CL_SECRET, token)
    apply_courtlistener_token(token)
    await audit_service.log_event(
        event_type=AuditEventType.SETTINGS_CHANGE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="integration",
        resource_id="courtlistener",
        ip_address=get_client_ip(request),
        details={"action": "courtlistener_token_set"},
    )
    return {"status": "saved", "source": "instance", "masked": _mask(token)}


@router.delete("/courtlistener")
async def clear_courtlistener_token(
    request: Request,
    current_user: TokenData = require_permission("admin.settings"),
):
    """Clear the instance token and revert the running service to the .env fallback."""
    await delete_secret(CL_SECRET)
    apply_courtlistener_token((settings.courtlistener_api_token or "").strip() or None)
    await audit_service.log_event(
        event_type=AuditEventType.SETTINGS_CHANGE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="integration",
        resource_id="courtlistener",
        ip_address=get_client_ip(request),
        details={"action": "courtlistener_token_cleared"},
    )
    return {"status": "cleared"}


# ----- Connector (file picker) credentials: Google Drive / OneDrive+SharePoint / Box / Dropbox -----
# Same dual model as the CourtListener token: the open-source install sets
# .env variables; desktop / private installs save them here (encrypted,
# instance-wide, applied immediately). Instance values beat .env.


class ConnectorCredentialsRequest(BaseModel):
    values: dict[str, str] = Field(..., description="settings-field -> value for this provider")


@router.get("/connectors")
async def connector_credentials_status(
    current_user: TokenData = require_permission("admin.settings"),
):
    """Per-provider status: configured, from where, masked values."""
    providers = [
        await connector_credentials.provider_status(p)
        for p in connector_credentials.CONNECTOR_PROVIDERS
    ]
    return {"providers": providers}


@router.post("/connectors/{provider}")
async def set_connector_credentials(
    provider: str,
    body: ConnectorCredentialsRequest,
    request: Request,
    current_user: TokenData = require_permission("admin.settings"),
):
    """Save a provider's credentials instance-wide and apply them immediately."""
    meta = connector_credentials.CONNECTOR_PROVIDERS.get(provider)
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown connector provider")
    allowed = set(meta["fields"])
    values = {k: v.strip() for k, v in body.values.items() if k in allowed and v and v.strip()}
    if not values:
        raise HTTPException(status_code=400, detail="No credential values provided")
    await set_secret(connector_credentials.secret_name(provider), json.dumps(values))
    connector_credentials.apply_values(provider, values)
    await audit_service.log_event(
        event_type=AuditEventType.SETTINGS_CHANGE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="integration",
        resource_id=f"connector_{provider}",
        ip_address=get_client_ip(request),
        details={"action": "connector_credentials_set", "fields": sorted(values)},
    )
    return await connector_credentials.provider_status(provider)


@router.delete("/connectors/{provider}")
async def clear_connector_credentials(
    provider: str,
    request: Request,
    current_user: TokenData = require_permission("admin.settings"),
):
    """Clear the instance credentials and revert the provider to its .env values."""
    if provider not in connector_credentials.CONNECTOR_PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown connector provider")
    await delete_secret(connector_credentials.secret_name(provider))
    connector_credentials.revert_to_env(provider)
    await audit_service.log_event(
        event_type=AuditEventType.SETTINGS_CHANGE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="integration",
        resource_id=f"connector_{provider}",
        ip_address=get_client_ip(request),
        details={"action": "connector_credentials_cleared"},
    )
    return await connector_credentials.provider_status(provider)


# ----- Custom / local OpenAI-compatible model endpoint (Ollama, vLLM, OpenRouter, ...) -----

LLM_SECRET = "local_llm_config"


class LocalLLMRequest(BaseModel):
    base_url: str = Field(..., min_length=4, max_length=400)  # e.g. http://localhost:11434/v1
    chat_model: str = Field(..., min_length=1, max_length=120)
    utility_model: str | None = Field(None, max_length=120)


@router.get("/local-llm")
async def local_llm_status(current_user: TokenData = require_permission("admin.settings")):
    """Current effective model endpoint config (custom endpoint or OpenAI default)."""
    cfg = llm_clients.get_runtime()
    return {
        "configured": bool(cfg.get("base_url")),
        "base_url": cfg.get("base_url"),
        "chat_model": cfg.get("chat_model"),
        "utility_model": cfg.get("utility_model"),
    }


@router.post("/local-llm")
async def set_local_llm(
    body: LocalLLMRequest,
    request: Request,
    current_user: TokenData = require_permission("admin.settings"),
):
    """Point the instance at a custom OpenAI-compatible endpoint and apply immediately."""
    payload = {
        "base_url": body.base_url.strip(),
        "chat_model": body.chat_model.strip(),
        "utility_model": (body.utility_model or "").strip() or body.chat_model.strip(),
    }
    await set_secret(LLM_SECRET, json.dumps(payload))
    llm_clients.set_runtime(**payload)
    await audit_service.log_event(
        event_type=AuditEventType.SETTINGS_CHANGE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="integration",
        resource_id="local_llm",
        ip_address=get_client_ip(request),
        details={"action": "local_llm_set", "base_url": payload["base_url"]},
    )
    return {"status": "saved", **payload}


@router.delete("/local-llm")
async def clear_local_llm(
    request: Request,
    current_user: TokenData = require_permission("admin.settings"),
):
    """Revert to the OpenAI defaults from settings (.env)."""
    await delete_secret(LLM_SECRET)
    llm_clients.set_runtime(
        base_url="",
        chat_model=settings.openai_chat_model,
        utility_model=settings.openai_utility_model,
    )
    await audit_service.log_event(
        event_type=AuditEventType.SETTINGS_CHANGE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="integration",
        resource_id="local_llm",
        ip_address=get_client_ip(request),
        details={"action": "local_llm_cleared"},
    )
    return {"status": "cleared"}
