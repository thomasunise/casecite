import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.responses.documents import (
    DocumentContentResponse,
    DocumentDeleteResponse,
)
from app.models.schemas import (
    ConnectorType,
    CreateFolderRequest,
    Document,
    DocumentList,
    DocumentStatus,
    DocumentTreeResponse,
    MoveDocumentRequest,
)
from app.routers._matter_deps import accessible_matter_ids as _accessible_matter_ids
from app.services import matters as matters_service
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData
from app.services.documents import document_service
from app.services.permissions import require_permission
from app.services.user_keys import UserAPIKeys
from app.utils.error_handler import handle_service_error
from app.utils.file_crypto import FileDecryptionError
from app.utils.ip_resolution import get_client_ip

# Validation config and helpers live in app/utils/upload_validation.py so the
# cloud picker imports apply the same checks as this direct upload route.
from app.utils.upload_validation import (
    ALLOWED_MIME_TYPES,
    EXTENSION_TO_MIME,
    read_upload_capped,
    sanitize_filename,
    validate_file_content,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=Document)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    matter_id: str | None = Form(default=None),
    current_user: TokenData = require_permission("documents.upload"),
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Upload and index a document. Requires authentication.

    Optional matter_id files the document under a matter the caller belongs to,
    making it visible to that matter's members. Omitted -> the caller's personal
    (owner-only) scope, i.e. the historical behavior.
    """
    # Reject filing into a matter the caller is not a member of (no cross-matter
    # writes). None stays personal/owner-only.
    if matter_id and not await matters_service.is_member(db, matter_id, current_user.user_id):
        raise HTTPException(status_code=403, detail="You are not a member of the specified matter.")

    user_keys = UserAPIKeys.from_request(request, user_id=current_user.user_id)
    safe_filename = sanitize_filename(file.filename)

    # Chunked read with a hard cap (rejects early on Content-Length; never
    # buffers an oversized body into memory).
    content = await read_upload_capped(file, settings.max_upload_size, request=request)

    content_type = file.content_type
    if content_type not in ALLOWED_MIME_TYPES:
        ext = safe_filename.lower().rsplit(".", 1)[-1] if "." in safe_filename else ""
        content_type = EXTENSION_TO_MIME.get(ext, content_type)

    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. "
            "Allowed: PDF, Word, Excel, PowerPoint, ODT, TXT, Markdown, CSV, TSV, "
            "HTML, JSON, EML, MSG, RTF",
        )

    is_valid, detected_type, error_msg = validate_file_content(content, content_type, safe_filename)
    if not is_valid:
        await audit_service.log_event(
            event_type=AuditEventType.SECURITY_ALERT,
            user_id=current_user.user_id,
            user_email=current_user.email,
            ip_address=get_client_ip(request),
            details={
                "action": "file_type_mismatch",
                "filename": safe_filename,
                "claimed_type": content_type,
                "detected_type": detected_type,
            },
            success=False,
        )
        raise HTTPException(
            status_code=415,
            detail="File content does not match file type. Please upload a valid file.",
        )

    type_config = ALLOWED_MIME_TYPES.get(content_type, {})
    max_size = type_config.get("max_size", settings.max_upload_size)
    if len(content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large for this type. Maximum size for {content_type} is {max_size / 1024 / 1024}MB",
        )

    try:
        doc = await document_service.upload_and_index(
            file_content=content,
            filename=safe_filename,
            content_type=content_type,
            user_id=current_user.user_id,
            user_keys=user_keys,
            matter_id=matter_id,
        )
        return doc
    except HTTPException:
        raise
    except Exception as e:  # surface a clean error, never a bare 500
        raise handle_service_error(e, "Failed to process document", logger)


@router.get("", response_model=DocumentList)
async def list_documents(
    source: ConnectorType | None = None,
    status: DocumentStatus | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: TokenData = require_permission("documents.view"),
    accessible_matters: set[str] = Depends(_accessible_matter_ids),
) -> DocumentList:
    """List documents for the current user (own + shared matters). Requires auth."""
    docs = await document_service.list_documents(
        user_id=current_user.user_id,
        source=source,
        status=status,
        limit=limit,
        offset=offset,
        accessible_matter_ids=accessible_matters,
    )
    return DocumentList(
        documents=docs,
        count=len(docs),
    )


@router.get("/tree", response_model=DocumentTreeResponse)
async def get_document_tree(
    current_user: TokenData = require_permission("documents.view"),
) -> DocumentTreeResponse:
    """Get document tree structure for filtering UI. Requires authentication."""
    tree = await document_service.get_document_tree(current_user.user_id)
    return tree


# ==================== Knowledge-base folders ====================
# NOTE: literal /folders routes MUST stay above the /{document_id} catch-alls.


@router.get("/folders")
async def list_folders(current_user: TokenData = require_permission("documents.view")) -> dict:
    """List the current user's knowledge-base folders."""
    return {"folders": document_service.list_folders(current_user.user_id)}


@router.post("/folders")
async def create_folder(
    body: CreateFolderRequest, current_user: TokenData = require_permission("documents.upload")
) -> dict:
    """Create a knowledge-base folder."""
    try:
        path = document_service.create_folder(current_user.user_id, body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"path": path, "folders": document_service.list_folders(current_user.user_id)}


@router.delete("/folders")
async def delete_folder(
    path: str = Query(..., description="Folder path to delete"),
    current_user: TokenData = require_permission("documents.delete"),
) -> dict:
    """Delete a folder; its documents move back to General (root)."""
    try:
        document_service.delete_folder(current_user.user_id, path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "deleted", "folders": document_service.list_folders(current_user.user_id)}


@router.post("/{document_id}/move")
async def move_document(
    document_id: str,
    body: MoveDocumentRequest,
    current_user: TokenData = require_permission("documents.upload"),
) -> dict:
    """Move a document into a folder (null/empty folder_path = General/root)."""
    try:
        ok = document_service.move_document(document_id, current_user.user_id, body.folder_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "moved", "folder_path": body.folder_path or None}


@router.get("/{document_id}/content", response_model=DocumentContentResponse)
async def get_document_content(
    document_id: str,
    request: Request,
    current_user: TokenData = require_permission("documents.view"),
    accessible_matters: set[str] = Depends(_accessible_matter_ids),
) -> DocumentContentResponse:
    """Get the extracted text content of a document. Requires authentication."""
    import os

    doc = await document_service.get_document(
        document_id, current_user.user_id, accessible_matter_ids=accessible_matters
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await audit_service.log_event(
        event_type=AuditEventType.DOCUMENT_VIEW,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="document",
        resource_id=document_id,
        ip_address=get_client_ip(request),
    )

    # Resolve the file under the OWNER's dir (doc.user_id) so a member reading a
    # shared document finds the owner's stored file.
    file_ext = os.path.splitext(doc.filename)[1]
    user_file_path = os.path.join(
        document_service._get_user_upload_dir(doc.user_id),
        f"{document_id}{file_ext}",
    )
    legacy_file_path = os.path.join(settings.upload_dir, f"{document_id}{file_ext}")

    file_path = None
    if os.path.exists(user_file_path):
        file_path = user_file_path
    elif os.path.exists(legacy_file_path):
        file_path = legacy_file_path

    if not file_path:
        raise HTTPException(
            status_code=404,
            detail="Document file not found on disk",
        )

    try:
        text = await document_service.extract_text(file_path, doc.content_type)
    except (ValueError, KeyError, OSError) as e:
        raise handle_service_error(e, "Failed to extract text from document", logger)

    return {
        "document_id": document_id,
        "text": text,
        "filename": doc.filename,
    }


# Content types that are safe to render inline in the browser. Anything else is
# served as a download so a document whose content-type is text/html (e.g. an
# imported file) can't execute script in the app origin (stored-XSS defense).
_INLINE_SAFE_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "text/plain",
}


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: str,
    request: Request,
    current_user: TokenData = require_permission("documents.view"),
    accessible_matters: set[str] = Depends(_accessible_matter_ids),
) -> Response:
    """Serve the original uploaded file as binary for visual rendering."""
    import os

    doc = await document_service.get_document(
        document_id, current_user.user_id, accessible_matter_ids=accessible_matters
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Resolve the file under the OWNER's dir (doc.user_id) so a shared document
    # is served from the owner's storage.
    file_ext = os.path.splitext(doc.filename)[1]
    user_file_path = os.path.join(
        document_service._get_user_upload_dir(doc.user_id),
        f"{document_id}{file_ext}",
    )
    legacy_file_path = os.path.join(settings.upload_dir, f"{document_id}{file_ext}")

    file_path = None
    if os.path.exists(user_file_path):
        file_path = user_file_path
    elif os.path.exists(legacy_file_path):
        file_path = legacy_file_path

    if not file_path:
        raise HTTPException(status_code=404, detail="Document file not found on disk")

    try:
        # Decrypts the at-rest encryption transparently (legacy plaintext passes through).
        file_bytes = await document_service.read_file(file_path)
    except (OSError, FileDecryptionError) as e:
        logger.error(f"Failed to read file {file_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to read document file")

    await audit_service.log_event(
        event_type=AuditEventType.DOCUMENT_DOWNLOAD,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="document",
        resource_id=document_id,
        ip_address=get_client_ip(request),
    )

    # Only render inline for a strict allowlist of safe types; everything else is
    # forced to download with a neutral type so an attacker-chosen content-type
    # (e.g. text/html from an import) can't run script in the app origin.
    declared_type = doc.content_type or "application/octet-stream"
    if declared_type in _INLINE_SAFE_CONTENT_TYPES:
        media_type = declared_type
        disposition = "inline"
    else:
        media_type = "application/octet-stream"
        disposition = "attachment"

    # RFC 5987-safe filename to keep quotes/newlines out of the header.
    safe_name = doc.filename.replace('"', "").replace("\r", "").replace("\n", "")

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{document_id}", response_model=Document)
async def get_document(
    document_id: str,
    current_user: TokenData = require_permission("documents.view"),
    accessible_matters: set[str] = Depends(_accessible_matter_ids),
) -> Document:
    """Get a specific document (own or shared via a matter). Requires auth."""
    doc = await document_service.get_document(
        document_id, current_user.user_id, accessible_matter_ids=accessible_matters
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: str,
    request: Request,
    current_user: TokenData = require_permission("documents.delete"),
    accessible_matters: set[str] = Depends(_accessible_matter_ids),
) -> DocumentDeleteResponse:
    """Delete a document (own or shared via a matter). Requires authentication."""
    try:
        success = await document_service.delete_document(
            document_id, current_user.user_id, accessible_matter_ids=accessible_matters
        )
        if not success:
            raise HTTPException(status_code=404, detail="Document not found")
    except HTTPException:
        raise
    except (ValueError, KeyError, OSError) as e:
        raise handle_service_error(e, "Failed to delete document", logger)

    try:
        await audit_service.log_event(
            event_type=AuditEventType.DOCUMENT_DELETE,
            user_id=current_user.user_id,
            user_email=current_user.email,
            resource_type="document",
            resource_id=document_id,
            ip_address=get_client_ip(request),
            details={"action": "document_deleted"},
        )
    except (ValueError, KeyError, OSError) as e:
        logger.error(f"Audit log error for document delete {document_id}: {e}")

    return {"status": "deleted", "id": document_id}
