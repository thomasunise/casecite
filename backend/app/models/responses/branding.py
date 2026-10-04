"""Branding response models."""

from pydantic import BaseModel


class BrandingLogoResponse(BaseModel):
    """POST /branding/logo."""

    status: str
    logo_url: str
