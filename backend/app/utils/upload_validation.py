"""
Shared upload validation: MIME allowlist, magic-byte content checks, and
filename sanitization.

Used by the direct upload route (routers/documents.py) and by every cloud
picker import (routers/pickers.py), so a file fetched from Google/OneDrive/
Box/Dropbox gets the same content validation as one uploaded from disk.
"""

from __future__ import annotations

import logging
import re

from fastapi import HTTPException, Request, UploadFile

logger = logging.getLogger(__name__)

# File validation configuration
ALLOWED_MIME_TYPES = {
    "application/pdf": {"max_size": 50 * 1024 * 1024, "extensions": [".pdf"]},  # 50MB
    "application/msword": {
        "max_size": 25 * 1024 * 1024,
        "extensions": [".doc"],
    },  # 25MB
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        "max_size": 25 * 1024 * 1024,
        "extensions": [".docx"],
    },
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
        "max_size": 25 * 1024 * 1024,
        "extensions": [".xlsx"],
    },
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": {
        "max_size": 25 * 1024 * 1024,
        "extensions": [".pptx"],
    },
    "application/vnd.ms-excel": {"max_size": 25 * 1024 * 1024, "extensions": [".xls"]},
    "application/vnd.oasis.opendocument.text": {
        "max_size": 25 * 1024 * 1024,
        "extensions": [".odt"],
    },
    "text/plain": {"max_size": 10 * 1024 * 1024, "extensions": [".txt"]},  # 10MB
    "text/markdown": {"max_size": 10 * 1024 * 1024, "extensions": [".md", ".markdown"]},
    "text/csv": {"max_size": 10 * 1024 * 1024, "extensions": [".csv"]},
    "text/tab-separated-values": {"max_size": 10 * 1024 * 1024, "extensions": [".tsv"]},
    "text/html": {"max_size": 10 * 1024 * 1024, "extensions": [".html", ".htm"]},
    "application/json": {"max_size": 10 * 1024 * 1024, "extensions": [".json"]},
    "message/rfc822": {"max_size": 25 * 1024 * 1024, "extensions": [".eml"]},
    "application/vnd.ms-outlook": {"max_size": 25 * 1024 * 1024, "extensions": [".msg"]},
    "text/rtf": {"max_size": 25 * 1024 * 1024, "extensions": [".rtf"]},
    "application/rtf": {"max_size": 25 * 1024 * 1024, "extensions": [".rtf"]},
}

# Kept for compatibility: the picker import path merges this over the main
# allowlist. xlsx/pptx were promoted into ALLOWED_MIME_TYPES (direct upload
# now accepts them too), so the entries here are identical duplicates.
PICKER_EXTRA_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
        "max_size": 25 * 1024 * 1024,
        "extensions": [".xlsx"],
    },
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": {
        "max_size": 25 * 1024 * 1024,
        "extensions": [".pptx"],
    },
}

_OOXML_TYPES = [
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
]

# Every allowed format carried in a PK zip container — libmagic and the
# signature fallback can only see "zip", so these all cross-match.
_ZIP_CONTAINER_TYPES = [*_OOXML_TYPES, "application/vnd.oasis.opendocument.text"]

# Every allowed format carried in an OLE compound file — same story: the
# container signature can't distinguish legacy Word from Excel from Outlook.
_OLE_CONTAINER_TYPES = [
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.ms-outlook",
]

# Magic bytes for file type detection
MAGIC_BYTES = {
    b"%PDF": "application/pdf",
    b"PK\x03\x04": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # OOXML zip
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1": "application/msword",  # OLE (doc/xls/msg)
}

EXTENSION_TO_MIME = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odt": "application/vnd.oasis.opendocument.text",
    "txt": "text/plain",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "html": "text/html",
    "htm": "text/html",
    "json": "application/json",
    "eml": "message/rfc822",
    "msg": "application/vnd.ms-outlook",
    "rtf": "application/rtf",
}

# Backwards-compatible private alias (older imports).
_EXTENSION_TO_MIME = EXTENSION_TO_MIME


def _detect_by_signature(content: bytes) -> str:
    """Manual magic-byte detection (fallback when libmagic is absent or unsure)."""
    for magic_bytes, mime_type in MAGIC_BYTES.items():
        if content.startswith(magic_bytes):
            return mime_type
    try:
        content[:1000].decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        return "application/octet-stream"


def validate_file_content(
    content: bytes, claimed_type: str, filename: str
) -> tuple[bool, str, str]:
    """
    Validate file content against claimed type using magic bytes.

    Returns: (is_valid, detected_type, error_message)
    """
    # Try python-magic first (most reliable)
    try:
        import magic

        detected_type = magic.from_buffer(content, mime=True)
        # libmagic answers octet-stream when it can't classify (it does this
        # for small/uncommon zip containers such as minimal OOXML exports).
        # That's "don't know", not "mismatch" — fall back to signature checks
        # so a legitimate file isn't rejected on an inconclusive answer.
        if not detected_type or detected_type == "application/octet-stream":
            detected_type = _detect_by_signature(content)
    except ImportError:
        detected_type = _detect_by_signature(content)
    except (ValueError, KeyError, OSError) as e:
        logger.warning(f"Magic detection failed: {e}")
        detected_type = claimed_type

    # Validate detected type matches claimed type (with some flexibility)
    text_family = [
        "text/markdown",
        "text/csv",
        "text/tab-separated-values",
        "text/html",
        "application/json",
        "message/rfc822",
        "text/rtf",
        "application/rtf",
    ]
    type_mappings = {
        # Any OOXML/ODF container is a zip; libmagic may report the generic
        # type or a sibling container type, so the whole family cross-matches.
        "application/zip": list(_ZIP_CONTAINER_TYPES),
        "application/x-zip-compressed": list(_ZIP_CONTAINER_TYPES),
        **{t: [o for o in _ZIP_CONTAINER_TYPES if o != t] for t in _ZIP_CONTAINER_TYPES},
        # Legacy Office and Outlook files share the OLE compound container;
        # libmagic sometimes reports the generic CDFV2/ms-office types.
        "application/x-ole-storage": list(_OLE_CONTAINER_TYPES),
        "application/CDFV2": list(_OLE_CONTAINER_TYPES),
        "application/vnd.ms-office": list(_OLE_CONTAINER_TYPES),
        **{t: [o for o in _OLE_CONTAINER_TYPES if o != t] for t in _OLE_CONTAINER_TYPES},
        # Text-based formats are all detected as text/plain by libmagic (and
        # html/json/eml may be detected as their specific type instead).
        "text/plain": list(text_family),
        **{t: ["text/plain"] for t in text_family},
        "text/rtf": ["application/rtf", "text/plain"],
        "application/rtf": ["text/rtf", "text/plain"],
        "text/csv": ["text/plain", "text/tab-separated-values"],
        "text/tab-separated-values": ["text/plain", "text/csv"],
    }

    is_match = (
        detected_type == claimed_type
        or claimed_type in type_mappings.get(detected_type, [])
        or detected_type in type_mappings.get(claimed_type, [])
    )

    if not is_match:
        return (
            False,
            detected_type,
            f"File content does not match claimed type. Detected: {detected_type}, Claimed: {claimed_type}",
        )

    return True, detected_type, ""


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and other attacks.

    - Removes path separators
    - Removes null bytes and control characters
    - Limits length
    - Preserves extension
    """
    if not filename:
        return "unnamed_file"

    # Remove path components (prevent path traversal)
    filename = filename.replace("\\", "/").split("/")[-1]

    # Remove null bytes and control characters
    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)

    # Remove dangerous characters
    filename = re.sub(r'[<>:"|?*]', "_", filename)

    # Remove leading/trailing dots and spaces
    filename = filename.strip(". ")

    # Limit length while preserving extension
    max_length = 255
    if len(filename) > max_length:
        name, ext = (filename.rsplit(".", 1) + [""])[:2]
        if ext:
            name = name[: max_length - len(ext) - 1]
            filename = f"{name}.{ext}"
        else:
            filename = filename[:max_length]

    return filename or "unnamed_file"


def validate_import_file(
    content: bytes, content_type: str | None, filename: str
) -> tuple[str, str]:
    """Validate a file fetched from a cloud picker before indexing it.

    Applies the same allowlist + magic-byte checks as the direct upload route
    (plus the OOXML export types Google Drive produces). Returns
    (safe_filename, resolved_content_type); raises ValueError on any failure —
    picker import loops already catch ValueError and report it per-file.
    """
    allowed = {**ALLOWED_MIME_TYPES, **PICKER_EXTRA_MIME_TYPES}
    safe_name = sanitize_filename(filename)

    resolved = content_type or ""
    if resolved not in allowed:
        ext = safe_name.lower().rsplit(".", 1)[-1] if "." in safe_name else ""
        resolved = _EXTENSION_TO_MIME.get(ext, resolved)
    if resolved not in allowed:
        raise ValueError(f"Unsupported file type: {content_type or 'unknown'}")

    # Size before content: it's the cheap check, and an oversized file should
    # be rejected without running content detection over the whole payload.
    max_size = allowed[resolved]["max_size"]
    if len(content) > max_size:
        raise ValueError(
            f"File too large for this type. Maximum size for {resolved} is "
            f"{max_size / 1024 / 1024}MB"
        )

    is_valid, detected_type, error_msg = validate_file_content(content, resolved, safe_name)
    if not is_valid:
        logger.warning(
            f"Picker import content mismatch for {safe_name}: "
            f"claimed={resolved} detected={detected_type}"
        )
        raise ValueError(error_msg)

    return safe_name, resolved


async def read_upload_capped(
    file: UploadFile,
    max_bytes: int,
    request: Request | None = None,
    chunk_size: int = 1024 * 1024,
) -> bytes:
    """Read an UploadFile with a hard byte ceiling, never buffering past it.

    Enforcement happens BEFORE/WHILE reading, not after:
    1. If *request* is given and its Content-Length header already exceeds the
       cap, reject immediately without reading the body.
    2. If Starlette resolved a size for the uploaded part, reject on that.
    3. Otherwise read in *chunk_size* pieces, raising as soon as the running
       total exceeds *max_bytes* — an oversized upload is never fully read
       into memory.

    Raises HTTPException(413) when the limit is exceeded.
    """

    def _too_large() -> HTTPException:
        return HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {max_bytes / 1024 / 1024}MB",
        )

    if request is not None:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise _too_large()

    declared_size = getattr(file, "size", None)
    if declared_size is not None and declared_size > max_bytes:
        raise _too_large()

    chunks = bytearray()
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        chunks.extend(chunk)
        if len(chunks) > max_bytes:
            raise _too_large()
    return bytes(chunks)
