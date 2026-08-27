"""
Branding / White-Label Service

Business logic for branding configuration persistence.
All database interactions are encapsulated here; the router delegates to this module.
"""

import logging
import os
import uuid
from datetime import datetime

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


def _serialize(row: BrandingConfigDB) -> dict:
    """Convert a BrandingConfigDB row to a response dict."""
    return {
        "firm_name": row.firm_name or DEFAULT_BRANDING["firm_name"],
        "logo_url": row.logo_url,
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
            row.logo_url = logo_url
        if primary_color is not None:
            row.primary_color = primary_color
        if secondary_color is not None:
            row.secondary_color = secondary_color
        if accent_color is not None:
            row.accent_color = accent_color
        if favicon_url is not None:
            row.favicon_url = favicon_url
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

    filename = f"brand_logo_{uuid.uuid4().hex[:8]}{ext}"
    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)

    with open(file_path, "wb") as f:
        f.write(contents)

    logo_url = f"/static/uploads/{filename}"

    async with get_db_context() as db:
        row = await _get_or_create_config(db)
        row.logo_url = logo_url
        row.updated_at = datetime.utcnow()
        await db.flush()

    return logo_url


async def reset_branding() -> dict:
    """Reset branding to platform defaults and return the result."""
    async with get_db_context() as db:
        row = await _get_or_create_config(db)

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
