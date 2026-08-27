"""User API key management response models."""

from pydantic import BaseModel


class KeySaveResponse(BaseModel):
    """POST /user/keys/save."""

    status: str
    key_type: str


class KeyMaskedResponse(BaseModel):
    """GET /user/keys/masked."""

    openai: str | None = None
    anthropic: str | None = None
    google: str | None = None
    voyage: str | None = None
    cohere: str | None = None
