"""
Branding / White-Label Router

Manage per-installation branding configuration (firm name, logo, colors, CSS).
The GET endpoint is public so the frontend can style itself on load.
All mutation endpoints require an admin role (branding is installation-wide).
Delegates all persistence to the branding service.
"""

import logging
import re

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.models.responses.branding import BrandingLogoResponse
from app.models.schemas import BrandingResponse, BrandingUpdate
from app.services.auth import TokenData
from app.services.branding import (
    get_branding as _get_branding,
)
from app.services.branding import (
    reset_branding as _reset_branding,
)
from app.services.branding import (
    update_branding as _update_branding,
)
from app.services.branding import (
    upload_logo as _upload_logo,
)
from app.services.permissions import require_permission
from app.utils.error_handler import handle_service_error
from app.utils.upload_validation import read_upload_capped

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/branding", tags=["branding"])


def _sanitize_custom_css(css: str | None) -> str | None:
    """Neutralize XSS vectors in operator-supplied custom CSS.

    custom_css is injected into a <style> block in the frontend, so an attacker
    who could set it might try to break out of the CSS context (``</style>...``)
    or use CSS-based script execution. We strip angle brackets (which have no
    legitimate use in CSS and enable </style> breakout) and known dangerous
    constructs. This runs even though only admins can now set branding, as
    defense in depth against an admin account compromise or CSRF.
    """
    if not css:
        return css
    # Remove anything that could close the style element or open a new tag.
    cleaned = css.replace("<", "").replace(">", "")
    # Strip constructs that can execute script from within CSS. Deleting a match
    # can splice a new one together (e.g. "javajavascript:script:"), so repeat
    # until a full pass removes nothing (fixpoint) instead of a single pass.
    dangerous = (r"(?i)javascript:", r"(?i)expression\s*\(", r"(?i)@import\b")
    while True:
        before = cleaned
        for pattern in dangerous:
            cleaned = re.sub(pattern, "", cleaned)
        if cleaned == before:
            return cleaned


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=BrandingResponse)
async def get_branding() -> BrandingResponse:
    """
    Get current branding configuration.

    This endpoint is **public** (no auth required) so the frontend can
    fetch brand assets on initial load before the user has logged in.
    Returns sensible defaults when no custom configuration has been saved.
    """
    return await _get_branding()


@router.put("", response_model=BrandingResponse)
async def update_branding(
    body: BrandingUpdate,
    current_user: TokenData = require_permission("admin.settings"),
) -> BrandingResponse:
    """
    Update branding configuration.

    Admin only — branding is installation-wide, so a non-admin must not be able
    to reskin or inject CSS for every user. Fields that are omitted (None) remain
    unchanged.
    """
    try:
        return await _update_branding(
            firm_name=body.firm_name,
            logo_url=body.logo_url,
            primary_color=body.primary_color,
            secondary_color=body.secondary_color,
            accent_color=body.accent_color,
            favicon_url=body.favicon_url,
            custom_css=_sanitize_custom_css(body.custom_css),
        )
    except (OSError, RuntimeError, ConnectionError, TimeoutError) as exc:
        raise handle_service_error(exc, "Failed to save branding", logger)


def _validate_logo_bytes(content_type: str, contents: bytes) -> None:
    """Verify uploaded logo bytes match the declared type; sanitize SVG.

    Raises HTTPException(400) on a magic-byte mismatch or a script-bearing SVG.
    """
    if content_type == "image/png" and not contents.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=400, detail="File is not a valid PNG image.")
    if content_type == "image/jpeg" and not contents.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=400, detail="File is not a valid JPEG image.")
    if content_type == "image/webp" and not (contents[:4] == b"RIFF" and contents[8:12] == b"WEBP"):
        raise HTTPException(status_code=400, detail="File is not a valid WebP image.")
    if content_type == "image/svg+xml":
        try:
            text = contents.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="SVG must be valid UTF-8 text.")
        low = text.lower()
        if "<svg" not in low:
            raise HTTPException(status_code=400, detail="File is not a valid SVG image.")
        # Reject active content that would execute in the app origin.
        forbidden = (
            "<script",
            "javascript:",
            "<foreignobject",
            "<iframe",
            "<embed",
            "<object",
            "<!entity",
            "<!doctype",
            "onload=",
            "onerror=",
            "onclick=",
            "onmouseover=",
            "onmouseenter=",
            "onbegin=",
            "onabort=",
            "onactivate=",
        )
        if any(tok in low for tok in forbidden):
            raise HTTPException(
                status_code=400,
                detail="SVG contains disallowed active content (scripts/handlers).",
            )


@router.post("/logo", response_model=BrandingLogoResponse)
async def upload_logo(
    request: Request,
    file: UploadFile = File(...),
    current_user: TokenData = require_permission("admin.settings"),
) -> BrandingLogoResponse:
    """
    Upload a logo image.

    Admin only. Accepts common image formats (PNG, JPEG, SVG, WebP).
    """
    allowed_types = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file.content_type}'. Allowed: PNG, JPEG, SVG, WebP.",
        )

    # 2 MB logo cap, enforced pre-read (Content-Length) and during a chunked
    # read — an oversized body is never fully buffered into memory.
    contents = await read_upload_capped(file, 2 * 1024 * 1024, request=request)

    # Don't trust the client-declared content type — verify the bytes match, and
    # neutralize script-bearing SVGs (stored-XSS in the app origin).
    _validate_logo_bytes(file.content_type, contents)

    logo_url = await _upload_logo(contents, file.content_type)
    logger.info("Logo uploaded by user %s", current_user.user_id)
    return {"status": "uploaded", "logo_url": logo_url}


@router.post("/reset", response_model=BrandingResponse)
async def reset_branding(
    current_user: TokenData = require_permission("admin.settings"),
) -> BrandingResponse:
    """
    Reset branding to platform defaults.

    Admin only. Clears all custom branding and restores built-in defaults.
    """
    return await _reset_branding()
