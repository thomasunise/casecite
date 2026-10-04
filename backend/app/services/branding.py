"""
Branding / White-Label Service

Business logic for branding configuration persistence.
All database interactions are encapsulated here; the router delegates to this module.
"""

import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import get_db_context
from app.models.db_models import BrandingConfigDB

logger = logging.getLogger(__name__)

DEFAULT_BRANDING: dict = {
    "firm_name": "CaseCite",
    "logo_url": None,
    "primary_color": "#E5E5E5",
    "secondary_color": "#0A0A0A",
    "accent_color": "#737373",
    "favicon_url": None,
    "custom_css": None,
}


# Uploaded logos live in their own directory on the data volume — NOT in the
# document upload dir, which holds encrypted client files and is never served.
# They are served (publicly, the login page needs them) by
# GET {api_prefix}/branding/assets/{filename} in app/routers/branding.py.
BRANDING_ASSET_DIR = Path(settings.upload_dir).parent / "branding"
ASSET_URL_PREFIX = f"{settings.api_prefix}/branding/assets/"
# The only filenames the asset route will ever serve (generated below).
ASSET_NAME_RE = re.compile(r"^brand_logo_[0-9a-f]{8,32}\.(png|jpg|svg|webp)$")
ASSET_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}
# Logos uploaded before the asset route existed were written into the upload
# dir and recorded under a /static/uploads/ URL that nothing served.
_LEGACY_URL_PREFIX = "/static/uploads/"


def resolve_asset_path(filename: str) -> Path | None:
    """Return the on-disk path of an uploaded branding asset, or None.

    Only generated ``brand_logo_<hex>.<ext>`` names are accepted, so the route
    cannot be used to read anything else off the data volume. Falls back to
    the legacy location (top level of the upload dir) for older uploads.
    """
    if not ASSET_NAME_RE.fullmatch(filename or ""):
        return None
    for directory in (BRANDING_ASSET_DIR, Path(settings.upload_dir)):
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


def _public_logo_url(stored: str | None) -> str | None:
    """Map a stored logo URL to one that is actually served."""
    if stored and stored.startswith(_LEGACY_URL_PREFIX):
        name = stored[len(_LEGACY_URL_PREFIX) :]
        return f"{ASSET_URL_PREFIX}{name}" if resolve_asset_path(name) else None
    return stored


def _remove_uploaded_asset(url: str | None) -> None:
    """Delete the file behind a previously uploaded logo URL (best effort)."""
    if not url:
        return
    for prefix in (ASSET_URL_PREFIX, _LEGACY_URL_PREFIX):
        if url.startswith(prefix):
            path = resolve_asset_path(url[len(prefix) :])
            if path is not None:
                try:
                    path.unlink()
                except OSError as exc:
                    logger.warning("Could not remove old branding asset %s: %s", path, exc)
            return


def _serialize(row: BrandingConfigDB) -> dict:
    """Convert a BrandingConfigDB row to a response dict."""
    return {
        "firm_name": row.firm_name or DEFAULT_BRANDING["firm_name"],
        "logo_url": _public_logo_url(row.logo_url),
        "primary_color": row.primary_color or DEFAULT_BRANDING["primary_color"],
        "secondary_color": row.secondary_color or DEFAULT_BRANDING["secondary_color"],
        "accent_color": row.accent_color or DEFAULT_BRANDING["accent_color"],
        "favicon_url": row.favicon_url,
        "custom_css": row.custom_css,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def _get_or_create_config(db) -> BrandingConfigDB:
    """Return the single branding config row, creating it with defaults if absent."""
    stmt = select(BrandingConfigDB).limit(1)
    result = await db.execute(stmt)
    row = result.scalars().first()

    if row is None:
        row = BrandingConfigDB(
            firm_name=DEFAULT_BRANDING["firm_name"],
            primary_color=DEFAULT_BRANDING["primary_color"],
            secondary_color=DEFAULT_BRANDING["secondary_color"],
            accent_color=DEFAULT_BRANDING["accent_color"],
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        await db.flush()

    return row


async def get_branding() -> dict:
    """Return current branding config, falling back to defaults on any DB error."""
    try:
        async with get_db_context() as db:
            stmt = select(BrandingConfigDB).limit(1)
            result = await db.execute(stmt)
            row = result.scalars().first()

            if row is None:
                return {**DEFAULT_BRANDING, "updated_at": None}

            return _serialize(row)
    except (OSError, RuntimeError, ConnectionError, TimeoutError) as exc:
        logger.warning("Could not load branding from DB, returning defaults: %s", exc)
        return {**DEFAULT_BRANDING, "updated_at": None}


async def update_branding(
    *,
    firm_name: str | None = None,
    logo_url: str | None = None,
    primary_color: str | None = None,
    secondary_color: str | None = None,
    accent_color: str | None = None,
    favicon_url: str | None = None,
    custom_css: str | None = None,
) -> dict:
    """Persist branding changes and return the updated config."""
    async with get_db_context() as db:
        row = await _get_or_create_config(db)

        if firm_name is not None:
            row.firm_name = firm_name
        if logo_url is not None:
            if logo_url != row.logo_url:
                _remove_uploaded_asset(row.logo_url)
            row.logo_url = logo_url or None
        if primary_color is not None:
            row.primary_color = primary_color
        if secondary_color is not None:
            row.secondary_color = secondary_color
        if accent_color is not None:
            row.accent_color = accent_color
        if favicon_url is not None:
            row.favicon_url = favicon_url or None
        if custom_css is not None:
            row.custom_css = custom_css

        row.updated_at = datetime.utcnow()
        await db.flush()
        return _serialize(row)


async def upload_logo(contents: bytes, content_type: str) -> str:
    """Save a logo file to disk and update the branding config.  Returns the public URL."""
    ext_map = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
    }
    ext = ext_map.get(content_type, ".png")

    filename = f"brand_logo_{uuid.uuid4().hex[:16]}{ext}"
    os.makedirs(BRANDING_ASSET_DIR, exist_ok=True)
    file_path = BRANDING_ASSET_DIR / filename

    with open(file_path, "wb") as f:
        f.write(contents)

    logo_url = f"{ASSET_URL_PREFIX}{filename}"

    async with get_db_context() as db:
        row = await _get_or_create_config(db)
        _remove_uploaded_asset(row.logo_url)
        row.logo_url = logo_url
        row.updated_at = datetime.utcnow()
        await db.flush()

    return logo_url


async def reset_branding() -> dict:
    """Reset branding to platform defaults and return the result."""
    async with get_db_context() as db:
        row = await _get_or_create_config(db)

        _remove_uploaded_asset(row.logo_url)
        row.firm_name = DEFAULT_BRANDING["firm_name"]
        row.logo_url = DEFAULT_BRANDING["logo_url"]
        row.primary_color = DEFAULT_BRANDING["primary_color"]
        row.secondary_color = DEFAULT_BRANDING["secondary_color"]
        row.accent_color = DEFAULT_BRANDING["accent_color"]
        row.favicon_url = DEFAULT_BRANDING["favicon_url"]
        row.custom_css = DEFAULT_BRANDING["custom_css"]
        row.updated_at = datetime.utcnow()
        await db.flush()
        return _serialize(row)
