"""Settings response models — prompt defaults and index clearing."""

from pydantic import BaseModel


class ModePrompts(BaseModel):
    """Mode-specific prompt defaults."""

    research: str
    case: str
    document: str
    compliance: str
    strategy: str


class PromptDefaultsResponse(BaseModel):
    """GET /settings/prompts/defaults."""

    system_prompt: str
    grounding_rules: str
    factual_prompt: str
    mode_prompts: ModePrompts


class ClearResponse(BaseModel):
    """POST /settings/clear."""

    status: str
    message: str
    cleared_documents: int | None = None
