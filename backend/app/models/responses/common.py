"""Common response models reused across multiple routers."""

from pydantic import BaseModel


class StatusResponse(BaseModel):
    """Generic status response (e.g., logout, toggle, action confirmations)."""

    status: str


class MessageResponse(BaseModel):
    """Generic message response (e.g., password reset, email confirmations)."""

    message: str


class DeletedResponse(BaseModel):
    """Response for deletion endpoints."""

    status: str = "deleted"
    id: str | None = None
