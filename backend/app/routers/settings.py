import logging

from fastapi import APIRouter, Depends

from app.models.responses.settings import ClearResponse, PromptDefaultsResponse
from app.models.schemas import RAGSettings
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData, get_current_user
from app.services.permissions import require_permission
from app.services.user_settings import load_user_settings, save_user_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/rag", response_model=RAGSettings)
async def get_rag_settings(current_user: TokenData = Depends(get_current_user)) -> RAGSettings:
    """Get current user's RAG settings. Requires authentication."""
    return load_user_settings(current_user.user_id)


@router.put("/rag", response_model=RAGSettings)
async def update_rag_settings(
    new_settings: RAGSettings, current_user: TokenData = Depends(get_current_user)
) -> RAGSettings:
    """Update RAG settings for the current user. Requires authentication."""
    # Log settings change for audit
    await audit_service.log_event(
        event_type=AuditEventType.SETTINGS_CHANGE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="rag_settings",
        details={"new_settings": new_settings.model_dump()},
    )

    save_user_settings(current_user.user_id, new_settings)
    return new_settings


@router.get("/prompts/defaults", response_model=PromptDefaultsResponse)
async def get_default_prompts(current_user: TokenData = Depends(get_current_user)) -> dict:
    """Get all default prompts for reset/customization functionality. Requires authentication."""
    from app.services.rag import rag_service

    return {
        "system_prompt": rag_service._get_default_system_prompt(),
        "grounding_rules": rag_service._get_default_grounding_rules(),
        "factual_prompt": rag_service._get_default_factual_prompt(),
        "mode_prompts": {
            "research": rag_service._get_default_mode_prompt("research"),
            "case": rag_service._get_default_mode_prompt("case"),
            "document": rag_service._get_default_mode_prompt("document"),
            "compliance": rag_service._get_default_mode_prompt("compliance"),
            "strategy": rag_service._get_default_mode_prompt("strategy"),
        },
    }


@router.post("/reindex")
async def trigger_reindex(current_user: TokenData = require_permission("admin.settings")) -> dict:
    """Trigger a reindex of the current user's documents."""
    from app.services.diagnostics import reindex_user_documents

    await audit_service.log_event(
        event_type=AuditEventType.SETTINGS_CHANGE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="index",
        details={"action": "reindex_started"},
    )

    return await reindex_user_documents(current_user.user_id)


@router.post("/clear", response_model=ClearResponse)
async def clear_index(current_user: TokenData = require_permission("admin.settings")) -> dict:
    """Clear the current user's documents and vectors."""
    # Log this critical action
    await audit_service.log_event(
        event_type=AuditEventType.SETTINGS_CHANGE,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="index",
        details={"action": "index_cleared", "warning": "User documents deleted"},
    )

    from app.services.documents import document_service

    try:
        result = await document_service.clear_all(current_user.user_id)
        return {
            "status": "cleared",
            "message": "Index cleared successfully. All your documents have been removed.",
            "cleared_documents": result.get("cleared_documents", 0),
        }
    except (ValueError, KeyError, OSError) as e:
        logger.error(f"Failed to clear index: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "Failed to clear index. Check server logs for details.",
        }
