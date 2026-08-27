"""
File Picker APIs - No OAuth Verification Required

These endpoints handle file selection via provider Picker APIs which use limited scopes
that don't require Google/Microsoft OAuth app verification. Users can select specific
files without granting full drive access.

Supported Pickers:
- Google Picker API (drive.file scope - no verification needed)
- Microsoft OneDrive File Picker (Files.Read.Selected scope)
- Box Content Picker (UI Elements)
- Dropbox Chooser (direct download links)
"""

import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.config import settings
from app.models.schemas import (
    BoxPickerFile,
    BoxPickerTokenResponse,
    ConnectorType,
    DropboxChooserFile,
    GooglePickerFile,
    OneDrivePickerFile,
    PickerConfig,
    PickerImportResponse,
)
from app.services import connector_credentials
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData, get_current_user
from app.services.documents import document_service
from app.services.permissions import require_permission
from app.utils.ip_resolution import get_client_ip
from app.utils.safe_fetch import UnsafeURLError, safe_download
from app.utils.upload_validation import validate_import_file

# Provider download hosts allowed for server-side fetches (suffix-matched).
# Content endpoints commonly 302-redirect to a CDN host, which safe_download
# re-validates against this list on each hop.
_MICROSOFT_HOSTS = (
    "graph.microsoft.com",
    "sharepoint.com",
    "1drv.com",
    "svc.ms",
    "onedrive.live.com",
    "live.com",
)
_BOX_HOSTS = ("box.com", "boxcloud.com")
_DROPBOX_HOSTS = ("dropbox.com", "dropboxusercontent.com")
_GOOGLE_HOSTS = ("googleapis.com", "googleusercontent.com")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pickers", tags=["file-pickers"])


# ============================================
# Configuration Endpoint
# ============================================


@router.get("/config", response_model=PickerConfig)
async def get_picker_config(current_user: TokenData = Depends(get_current_user)) -> PickerConfig:
    """
    Get picker configuration for frontend. Requires authentication.
    Returns only client IDs and enabled flags - no sensitive API keys.
    Actual API keys are stored server-side only.
    """
    return PickerConfig(
        # Google Picker - only return client ID, not API key
        google_enabled=bool(
            connector_credentials.get("google_api_key")
            and connector_credentials.get("google_client_id")
        ),
        google_api_key=None,  # Don't expose API key to client
        google_client_id=connector_credentials.get("google_client_id"),
        google_app_id=connector_credentials.get("google_app_id"),
        # Microsoft OneDrive Picker
        microsoft_enabled=bool(connector_credentials.get("microsoft_client_id")),
        microsoft_client_id=connector_credentials.get("microsoft_client_id"),
        microsoft_tenant_id=connector_credentials.get("microsoft_tenant_id") or "common",
        # Box Content Picker
        box_enabled=bool(connector_credentials.get("box_client_id")),
        box_client_id=connector_credentials.get("box_client_id"),
        # Dropbox Chooser
        dropbox_enabled=bool(connector_credentials.get("dropbox_app_key")),
        dropbox_app_key=connector_credentials.get("dropbox_app_key"),
    )


# ============================================
# Box Picker Token
# ============================================


@router.get("/box/token", response_model=BoxPickerTokenResponse)
async def get_box_picker_token(
    current_user: TokenData = Depends(get_current_user),
) -> BoxPickerTokenResponse:
    """
    Get a downscoped Box token for the browser-side Content Picker.

    Requires the Box connector to be OAuth-connected for this user; the
    stored token is exchanged for one limited to picking and downloading.
    """
    from app.services.connectors import get_connector
    from app.services.connectors.base import BaseConnector

    BaseConnector.set_current_user(current_user.user_id)
    connector = get_connector(ConnectorType.BOX)

    if not connector.is_configured:
        raise HTTPException(status_code=400, detail="Box is not configured on this server.")
    if not connector.is_connected:
        raise HTTPException(
            status_code=409,
            detail="Box account not connected. Connect Box before using the picker.",
        )

    try:
        token = await connector.get_downscoped_token()
    except (httpx.HTTPError, KeyError):
        logger.error("Box token downscope failed", exc_info=True)
        raise HTTPException(status_code=502, detail="Could not obtain a Box picker token.")

    return BoxPickerTokenResponse(**token)


# ============================================
# Google Picker Import
# ============================================


@router.post("/google/import")
async def import_from_google_picker(
    files: list[GooglePickerFile],
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: TokenData = require_permission("documents.upload"),
) -> PickerImportResponse:
    """
    Import files selected via Google Picker.

    The Google Picker returns an OAuth token scoped only to the selected files,
    which doesn't require OAuth app verification.
    """
    imported = 0
    failed = 0
    errors = []

    for file in files:
        try:
            # Check if it's a Google Docs file that needs export
            export_mimes = {
                "application/vnd.google-apps.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.google-apps.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            }

            headers = {"Authorization": f"Bearer {file.oauthToken}"}

            if file.mimeType in export_mimes:
                # Export Google Docs format to Office format
                query = urlencode({"mimeType": export_mimes[file.mimeType]})
                url = f"https://www.googleapis.com/drive/v3/files/{file.id}/export?{query}"

                # Adjust filename extension
                ext_map = {
                    "application/vnd.google-apps.document": ".docx",
                    "application/vnd.google-apps.spreadsheet": ".xlsx",
                    "application/vnd.google-apps.presentation": ".pptx",
                }
                filename = file.name
                if not filename.endswith(ext_map.get(file.mimeType, "")):
                    filename += ext_map.get(file.mimeType, "")
                content_type = export_mimes[file.mimeType]
            else:
                # Direct download
                url = f"https://www.googleapis.com/drive/v3/files/{file.id}?{urlencode({'alt': 'media'})}"
                filename = file.name
                content_type = file.mimeType

            content = await safe_download(
                url,
                headers=headers,
                max_bytes=settings.max_upload_size,
                allowed_hosts=_GOOGLE_HOSTS,
            )

            # Same allowlist + magic-byte validation as the direct upload route.
            filename, content_type = validate_import_file(content, content_type, filename)

            # Index the document
            await document_service.upload_and_index(
                file_content=content,
                filename=filename,
                content_type=content_type,
                user_id=current_user.user_id,
                source=ConnectorType.GOOGLE_PICKER,
                source_id=file.id,
                metadata={"original_url": file.url},
            )
            imported += 1

        except UnsafeURLError as e:
            logger.warning(f"Blocked unsafe Google import URL for {file.name}: {e}")
            errors.append(f"{file.name}: download URL rejected")
            failed += 1
        except (ValueError, KeyError, ConnectionError, TimeoutError, OSError, httpx.HTTPError) as e:
            logger.error(f"Failed to import Google file {file.name}: {e}")
            errors.append(f"{file.name}: {str(e)}")
            failed += 1

    # Audit log
    await audit_service.log_event(
        event_type=AuditEventType.DOCUMENT_UPLOAD,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="picker_import",
        resource_id="google_picker",
        ip_address=get_client_ip(request),
        details={"imported": imported, "failed": failed, "provider": "google_picker"},
    )

    return PickerImportResponse(imported=imported, failed=failed, errors=errors)


# ============================================
# Microsoft OneDrive Picker Import
# ============================================


@router.post("/microsoft/import")
async def import_from_onedrive_picker(
    files: list[OneDrivePickerFile],
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: TokenData = require_permission("documents.upload"),
) -> PickerImportResponse:
    """
    Import files selected via Microsoft OneDrive File Picker.

    The OneDrive Picker provides access tokens scoped to selected files only,
    which doesn't require admin consent for most organizations.
    """
    imported = 0
    failed = 0
    errors = []

    for file in files:
        try:
            headers = {"Authorization": f"Bearer {file.accessToken}"}
            # Use direct download URL if provided, otherwise fetch via Graph API.
            if file.downloadUrl:
                url = file.downloadUrl
            elif file.driveId:
                # SharePoint/shared drive file — use driveId-based path
                url = f"https://graph.microsoft.com/v1.0/drives/{file.driveId}/items/{file.id}/content"
            else:
                url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file.id}/content"

            content = await safe_download(
                url,
                headers=headers,
                max_bytes=settings.max_upload_size,
                allowed_hosts=_MICROSOFT_HOSTS,
            )

            # Determine content type from filename
            content_type = _guess_content_type(file.name)

            # Same allowlist + magic-byte validation as the direct upload route.
            safe_name, content_type = validate_import_file(content, content_type, file.name)

            # Index the document
            await document_service.upload_and_index(
                file_content=content,
                filename=safe_name,
                content_type=content_type,
                user_id=current_user.user_id,
                source=ConnectorType.ONEDRIVE_PICKER,
                source_id=file.id,
                metadata={"web_url": file.webUrl},
            )
            imported += 1

        except UnsafeURLError as e:
            logger.warning(f"Blocked unsafe OneDrive import URL for {file.name}: {e}")
            errors.append(f"{file.name}: download URL rejected")
            failed += 1
        except (ValueError, KeyError, ConnectionError, TimeoutError, OSError, httpx.HTTPError) as e:
            logger.error(f"Failed to import OneDrive file {file.name}: {e}")
            errors.append(f"{file.name}: {str(e)}")
            failed += 1

    # Audit log
    await audit_service.log_event(
        event_type=AuditEventType.DOCUMENT_UPLOAD,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="picker_import",
        resource_id="onedrive_picker",
        ip_address=get_client_ip(request),
        details={"imported": imported, "failed": failed, "provider": "onedrive_picker"},
    )

    return PickerImportResponse(imported=imported, failed=failed, errors=errors)


# ============================================
# Box Content Picker Import
# ============================================


@router.post("/box/import")
async def import_from_box_picker(
    files: list[BoxPickerFile],
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: TokenData = require_permission("documents.upload"),
) -> PickerImportResponse:
    """
    Import files selected via Box Content Picker (UI Elements).
    """
    imported = 0
    failed = 0
    errors = []

    for file in files:
        try:
            url = f"https://api.box.com/2.0/files/{file.id}/content"
            headers = {"Authorization": f"Bearer {file.accessToken}"}
            content = await safe_download(
                url,
                headers=headers,
                max_bytes=settings.max_upload_size,
                allowed_hosts=_BOX_HOSTS,
            )

            content_type = _guess_content_type(file.name)

            # Same allowlist + magic-byte validation as the direct upload route.
            safe_name, content_type = validate_import_file(content, content_type, file.name)

            await document_service.upload_and_index(
                file_content=content,
                filename=safe_name,
                content_type=content_type,
                user_id=current_user.user_id,
                source=ConnectorType.BOX_PICKER,
                source_id=file.id,
                metadata={},
            )
            imported += 1

        except UnsafeURLError as e:
            logger.warning(f"Blocked unsafe Box import URL for {file.name}: {e}")
            errors.append(f"{file.name}: download URL rejected")
            failed += 1
        except (ValueError, KeyError, ConnectionError, TimeoutError, OSError, httpx.HTTPError) as e:
            logger.error(f"Failed to import Box file {file.name}: {e}")
            errors.append(f"{file.name}: {str(e)}")
            failed += 1

    await audit_service.log_event(
        event_type=AuditEventType.DOCUMENT_UPLOAD,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="picker_import",
        resource_id="box_picker",
        ip_address=get_client_ip(request),
        details={"imported": imported, "failed": failed, "provider": "box_picker"},
    )

    return PickerImportResponse(imported=imported, failed=failed, errors=errors)


# ============================================
# Dropbox Chooser Import
# ============================================


@router.post("/dropbox/import")
async def import_from_dropbox_chooser(
    files: list[DropboxChooserFile],
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: TokenData = require_permission("documents.upload"),
) -> PickerImportResponse:
    """
    Import files selected via Dropbox Chooser.

    Dropbox Chooser provides direct download links that are valid for 4 hours.
    No OAuth token needed - the link itself contains authorization.
    """
    imported = 0
    failed = 0
    errors = []

    for file in files:
        try:
            # Dropbox Chooser provides direct download links on Dropbox hosts.
            content = await safe_download(
                file.link,
                max_bytes=settings.max_upload_size,
                allowed_hosts=_DROPBOX_HOSTS,
            )

            content_type = _guess_content_type(file.name)

            # Same allowlist + magic-byte validation as the direct upload route.
            safe_name, content_type = validate_import_file(content, content_type, file.name)

            await document_service.upload_and_index(
                file_content=content,
                filename=safe_name,
                content_type=content_type,
                user_id=current_user.user_id,
                source=ConnectorType.DROPBOX_CHOOSER,
                source_id=file.link,  # Use link as ID since Chooser doesn't provide file ID
                metadata={},
            )
            imported += 1

        except UnsafeURLError as e:
            logger.warning(f"Blocked unsafe Dropbox import URL for {file.name}: {e}")
            errors.append(f"{file.name}: download URL rejected")
            failed += 1
        except (ValueError, KeyError, ConnectionError, TimeoutError, OSError, httpx.HTTPError) as e:
            logger.error(f"Failed to import Dropbox file {file.name}: {e}")
            errors.append(f"{file.name}: {str(e)}")
            failed += 1

    await audit_service.log_event(
        event_type=AuditEventType.DOCUMENT_UPLOAD,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="picker_import",
        resource_id="dropbox_chooser",
        ip_address=get_client_ip(request),
        details={"imported": imported, "failed": failed, "provider": "dropbox_chooser"},
    )

    return PickerImportResponse(imported=imported, failed=failed, errors=errors)


# ============================================
# Helpers
# ============================================


def _guess_content_type(filename: str) -> str:
    """Guess MIME type from filename extension."""
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    mime_map = {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain",
        "rtf": "application/rtf",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "ppt": "application/vnd.ms-powerpoint",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "html": "text/html",
        "htm": "text/html",
        "csv": "text/csv",
        "json": "application/json",
        "xml": "application/xml",
        "md": "text/markdown",
    }
    return mime_map.get(ext, "application/octet-stream")
