"""Document management response models."""

from pydantic import BaseModel


class DocumentContentResponse(BaseModel):
    """GET /documents/{document_id}/content."""

    document_id: str
    text: str
    filename: str


class DocumentDeleteResponse(BaseModel):
    """DELETE /documents/{document_id}."""

    status: str
    id: str
