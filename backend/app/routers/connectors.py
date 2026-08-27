import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from app.models.responses.common import StatusResponse
from app.models.responses.connectors import (
    ConnectorCallbackResponse,
    ConnectorListResponse,
    SyncStartResponse,
)
from app.models.schemas import (
    ConnectorAuthUrl,
    ConnectorStatus,
    ConnectorType,
    SyncStatus,
)
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData
from app.services.connectors import get_all_connector_statuses, get_connector
from app.services.connectors.base import BaseConnector
from app.services.connectors.sync_state import (
    get_sync_owner,
    set_sync_owner,
    store_oauth_state,
    sync_statuses,
    validate_oauth_state,
)
from app.services.documents import document_service
from app.services.job_queue import RETRY_POLICIES, job_manager
from app.services.permissions import require_permission
from app.utils.ip_resolution import get_client_ip

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("", response_model=ConnectorListResponse)
async def list_connectors(
    current_user: TokenData = require_permission("connectors.manage"),
) -> ConnectorListResponse:
    """Get status of all connectors. Requires authentication."""
    BaseConnector.set_current_user(current_user.user_id)
    statuses = await get_all_connector_statuses()
    # Add id field matching connector type for frontend lookup
    for s in statuses:
        s["id"] = s.get("type", "")
    return {"connectors": statuses}


@router.get("/{connector_type}/status", response_model=ConnectorStatus)
async def get_connector_status(
    connector_type: ConnectorType, current_user: TokenData = require_permission("connectors.manage")
) -> ConnectorStatus:
    """Get status of a specific connector. Requires authentication."""
    BaseConnector.set_current_user(current_user.user_id)
    connector = get_connector(connector_type)
    status = await connector.get_status()
    return ConnectorStatus(
        type=connector_type,
        connected=status.get("connected", False),
        configured=status.get("configured", True),
        account_name=status.get("account_name"),
        account_email=status.get("account_email"),
        docs_indexed=status.get("docs_indexed", 0),
        last_sync=status.get("last_sync"),
    )


@router.get("/{connector_type}/auth", response_model=ConnectorAuthUrl)
async def get_auth_url(
    connector_type: ConnectorType, current_user: TokenData = require_permission("connectors.manage")
) -> ConnectorAuthUrl:
    """Get OAuth authorization URL for a connector. Requires authentication."""
    BaseConnector.set_current_user(current_user.user_id)
    connector = get_connector(connector_type)

    # Check if connector has required credentials configured
    if not connector.is_configured:
        raise HTTPException(
            status_code=400,
            detail=f"{connector_type.value} is not configured. An administrator needs to set up OAuth credentials for this connector.",
        )

    state = str(uuid.uuid4())

    # Store state with user binding and expiry for validation in callback
    store_oauth_state(state, current_user.user_id, connector_type)

    auth_url = connector.get_auth_url(state)

    return ConnectorAuthUrl(auth_url=auth_url, state=state)


@router.get("/{connector_type}/callback", response_model=ConnectorCallbackResponse)
async def handle_callback(
    connector_type: ConnectorType, code: str, state: str, request: Request
) -> ConnectorCallbackResponse:
    """Handle OAuth callback from connector.

    Security:
    - Validates state exists and is not expired
    - Validates state matches the connector type
    - State is single-use (deleted after validation to prevent replay)
    - Credentials stored under the user who initiated the OAuth flow
    """
    # Validate OAuth state (provides CSRF protection and user binding)
    user_id = validate_oauth_state(state, connector_type)
    if not user_id:
        await audit_service.log_event(
            event_type=AuditEventType.SECURITY_ALERT,
            ip_address=get_client_ip(request),
            details={
                "action": "oauth_callback_invalid_state",
                "connector_type": connector_type.value,
                "reason": "state_invalid_expired_or_mismatched",
            },
            success=False,
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OAuth state. Please try connecting again.",
        )

    # Set user context so credentials are stored for the correct user
    BaseConnector.set_current_user(user_id)
    connector = get_connector(connector_type)

    try:
        account_info = await connector.handle_callback(code, state)

        # Log the connection with user attribution
        await audit_service.log_event(
            event_type=AuditEventType.CONNECTOR_CONNECT,
            user_id=user_id,
            resource_type="connector",
            resource_id=connector_type.value,
            ip_address=get_client_ip(request),
            details={"account": account_info.get("email") or account_info.get("name")},
        )

        return {"status": "connected", "account": account_info}
    except (ValueError, KeyError, ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Connector callback error for {connector_type}: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to connect. Please try again.")


@router.post("/{connector_type}/disconnect", response_model=StatusResponse)
async def disconnect_connector(
    connector_type: ConnectorType,
    request: Request,
    current_user: TokenData = require_permission("connectors.manage"),
) -> StatusResponse:
    """Disconnect a connector. Requires authentication."""
    BaseConnector.set_current_user(current_user.user_id)
    connector = get_connector(connector_type)
    await connector.disconnect()

    # Log the disconnection
    await audit_service.log_event(
        event_type=AuditEventType.CONNECTOR_DISCONNECT,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="connector",
        resource_id=connector_type.value,
        ip_address=get_client_ip(request),
    )

    return {"status": "disconnected"}


@router.post("/{connector_type}/sync", response_model=SyncStartResponse)
async def start_sync(
    connector_type: ConnectorType,
    request: Request,
    folder_id: str | None = None,
    current_user: TokenData = require_permission("connectors.manage"),
) -> SyncStartResponse:
    """Start syncing documents from a connector. Requires authentication."""
    BaseConnector.set_current_user(current_user.user_id)
    connector = get_connector(connector_type)

    if not connector.is_connected:
        raise HTTPException(status_code=400, detail="Connector not connected")

    user_id = current_user.user_id
    user_email = current_user.email
    client_ip = get_client_ip(request)

    # Log sync start
    await audit_service.log_event(
        event_type=AuditEventType.CONNECTOR_SYNC_START,
        user_id=user_id,
        user_email=user_email,
        resource_type="connector",
        resource_id=connector_type.value,
        ip_address=client_ip,
        details={"folder_id": folder_id},
    )

    async def do_sync():
        return await run_sync(
            sync_id=None,  # Not used in new flow
            connector=connector,
            connector_type=connector_type,
            folder_id=folder_id,
            user_id=user_id,
            user_email=user_email,
        )

    # Submit to job_manager for Redis-backed persistence
    job_id = await job_manager.submit(
        do_sync,
        user_id=user_id,
        endpoint=f"/connectors/{connector_type.value}/sync",
        retry_policy=RETRY_POLICIES["external_api"],
    )

    # Also maintain legacy in-memory tracking for backward compatibility
    sync_statuses[job_id] = SyncStatus(connector=connector_type, status="syncing", progress=0.0)
    set_sync_owner(job_id, user_id)

    return {"sync_id": job_id, "status": "started"}


@router.get("/{connector_type}/sync/{sync_id}")
async def get_sync_status_endpoint(
    connector_type: ConnectorType,
    sync_id: str,
    current_user: TokenData = require_permission("connectors.manage"),
) -> dict:
    """Get status of a sync operation. Requires authentication and ownership."""
    # Check job_manager first (Redis-backed)
    job_data = job_manager.get_job(sync_id, current_user.user_id)
    if job_data:
        return job_data

    # Fallback to legacy in-memory tracking
    if sync_id not in sync_statuses:
        raise HTTPException(status_code=404, detail="Sync not found")

    if get_sync_owner(sync_id) != current_user.user_id:
        raise HTTPException(status_code=404, detail="Sync not found")

    return sync_statuses[sync_id]


async def run_sync(
    sync_id: str | None,
    connector,
    connector_type: ConnectorType,
    folder_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
) -> dict:
    """Background task to sync documents from a connector. Returns result dict."""
    # Restore user context in the background task (contextvars don't propagate)
    if user_id:
        BaseConnector.set_current_user(user_id)

    processed = 0
    errors = []

    try:
        # Crawl all files
        files = []
        async for file_info in connector.crawl_all_files():
            files.append(file_info)

        logger.info(f"Sync: Found {len(files)} files to process")

        # Process each file
        for i, file_info in enumerate(files):
            try:
                # Download file
                content = await connector.download_file(file_info.id)

                # Index it (user_id ensures proper document scoping)
                await document_service.upload_and_index(
                    file_content=content,
                    filename=file_info.name,
                    content_type=file_info.mime_type,
                    source=connector_type,
                    source_id=file_info.id,
                    metadata=file_info.metadata,
                    user_id=user_id,
                )

                processed += 1

            except (ValueError, KeyError, ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"Sync: Error processing {file_info.name}: {e}")
                errors.append(f"{file_info.name}: {str(e)}")
                continue

        # Update connector's last sync time
        connector.credentials["last_sync"] = datetime.now(UTC).isoformat()
        connector._save_credentials()

        # Log successful completion
        await audit_service.log_event(
            event_type=AuditEventType.CONNECTOR_SYNC_COMPLETE,
            user_id=user_id,
            user_email=user_email,
            resource_type="connector",
            resource_id=connector_type.value,
            details={
                "docs_processed": processed,
                "errors_count": len(errors),
            },
        )
        logger.info(f"Sync: Completed. Processed {processed} files, {len(errors)} errors")

        return {
            "status": "completed",
            "docs_processed": processed,
            "docs_total": len(files),
            "errors_count": len(errors),
            "errors": errors[:20],  # Cap error list for serialisation
        }

    except (ValueError, KeyError, ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Sync: Failed with error: {e}")

        # Log failure
        await audit_service.log_event(
            event_type=AuditEventType.CONNECTOR_SYNC_FAILURE,
            user_id=user_id,
            user_email=user_email,
            resource_type="connector",
            resource_id=connector_type.value,
            details={"error": str(e)},
            success=False,
            error=str(e),
        )
        raise
