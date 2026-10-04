import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# Enums
class ConnectorType(str, Enum):
    GOOGLE_DRIVE = "google_drive"
    ONEDRIVE = "onedrive"
    BOX = "box"
    NETDOCUMENTS = "netdocuments"
    IMANAGE = "imanage"
    FILEVINE = "filevine"
    CLIO = "clio"
    DROPBOX = "dropbox"
    LOCAL = "local"
    # Picker-based imports (no OAuth verification required)
    GOOGLE_PICKER = "google_picker"
    ONEDRIVE_PICKER = "onedrive_picker"
    BOX_PICKER = "box_picker"
    DROPBOX_CHOOSER = "dropbox_chooser"


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class CitationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AnalysisMode(str, Enum):
    RESEARCH = "research"
    CASE = "case"
    DOCUMENT = "document"
    COMPLIANCE = "compliance"
    STRATEGY = "strategy"


class QueryIntent(str, Enum):
    """Detected intent of a query - determines response verbosity."""

    FACTUAL = "factual"  # Simple questions: what, when, where, who, how many
    ANALYTICAL = "analytical"  # Complex analysis: strategy, compare, assess, recommend


# Request/Response Models
class DocumentFilter(BaseModel):
    """Filter for selecting which documents to search."""

    document_ids: list[str] | None = None  # Specific document IDs to include
    folder_paths: list[str] | None = None  # Folder paths to include (e.g., "/Cases/Smith v Jones/")
    sources: list[ConnectorType] | None = None  # Filter by source (google_drive, onedrive, etc.)
    doc_types: list[str] | None = None  # Filter by document type (contract, brief, memo, etc.)
    include_subfolders: bool = True  # Whether to include documents in subfolders
    search_all: bool = False  # If True, ignore other filters and search all documents


class CreateFolderRequest(BaseModel):
    """Create a knowledge-base folder."""

    name: str = Field(..., min_length=1, max_length=200)


class MoveDocumentRequest(BaseModel):
    """Move a document into a folder (null/empty = General/root)."""

    folder_path: str | None = None


class ChatRequest(BaseModel):
    """Request model for chat/RAG queries with validation."""

    query: str = Field(..., min_length=1, max_length=100000, description="The query text")
    mode: AnalysisMode = AnalysisMode.RESEARCH
    conversation_id: str | None = Field(None, max_length=100)
    # Persisted chat session to append this exchange to (None = start a new one).
    session_id: str | None = Field(None, max_length=100)
    include_citations: bool = True
    include_documents: bool = True  # Search uploaded documents (RAG)
    # None = decide automatically per message; explicit bool is respected.
    include_case_law: bool | None = None
    case_law_limit: int = Field(default=5, ge=1, le=50, description="Max case law results")
    document_filter: DocumentFilter | None = None  # Filter which documents to search

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate and sanitize query text."""
        v = v.strip()
        if not v:
            raise ValueError("Query cannot be empty")
        # Remove null bytes and control characters
        v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v)
        return v

    @field_validator("conversation_id", "session_id")
    @classmethod
    def validate_conversation_id(cls, v: str | None) -> str | None:
        """Validate conversation/session ID format."""
        if v is not None:
            v = v.strip()
            # Only allow alphanumeric, hyphens, and underscores
            if not re.match(r"^[a-zA-Z0-9_-]+$", v):
                raise ValueError("Invalid conversation ID format")
        return v


class StrategyBriefRequest(BaseModel):
    """Request model for a matter-level strategy brief with per-document coverage."""

    question: str = Field(..., min_length=1, max_length=10000, description="The strategy question")
    folder_path: str | None = Field(None, max_length=1000)  # Scope to a knowledge-base folder
    document_ids: list[str] | None = None  # Scope to specific documents
    include_case_law: bool = False  # Attach supporting case law to the strongest points

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        """Validate and sanitize the question text."""
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty")
        # Remove null bytes and control characters
        v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v)
        return v


class ReasoningStep(BaseModel):
    type: str
    description: str
    evidence: str | None = None


class CitationLogic(BaseModel):
    query_intent: str
    matching_criteria: str
    application: str


class Citation(BaseModel):
    id: str
    source: str
    type: str
    confidence: float
    status: CitationStatus = CitationStatus.PENDING
    similarity: float
    relevance_rank: int
    chunk_index: int
    token_count: int
    passage: str
    reasoning: list[ReasoningStep]
    # One-sentence LLM explanation of how this source supports the final answer
    # (populated by the post-answer citation-reasoning pass; None if unavailable).
    application: str | None = None
    # Short summary of what the case is about and its holding (case-law
    # citations only; written by the pre-answer relevance judge).
    case_summary: str | None = None
    logic: CitationLogic
    notes: str | None = None
    reviewed_at: datetime | None = None
    document_id: str | None = None
    url: str | None = None  # Link to source (e.g., CourtListener URL)
    was_cited_by_ai: bool = False  # Whether AI actually referenced this in response
    # Claim-grounded citations: whether the quote verified verbatim against
    # the source file, and where it sits (char span) so the UI can anchor it
    # inside the opened document.
    verified: bool | None = None
    doc_span_start: int | None = None
    doc_span_end: int | None = None


class ChatStats(BaseModel):
    docs_searched: int
    chunks_retrieved: int
    processing_time: str
    case_law_searched: int = 0  # CourtListener cases found
    case_law_included: int = 0  # Cases included in context
    query_intent: str | None = None  # "factual" or "analytical" - detected intent


class ConversationExportCitation(BaseModel):
    label: str = Field(..., min_length=1, max_length=500)
    quote: str | None = Field(None, max_length=5000)
    url: str | None = Field(None, max_length=1000)


class ConversationExportMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field("", max_length=200_000)
    citations: list[ConversationExportCitation] = Field(default_factory=list, max_length=200)


class ConversationExportRequest(BaseModel):
    """A chat transcript (as displayed) to render as a downloadable file."""

    title: str = Field("Conversation", max_length=300)
    format: Literal["docx", "pdf", "md"] = "docx"
    messages: list[ConversationExportMessage] = Field(..., min_length=1, max_length=500)


class ChatResponse(BaseModel):
    id: str
    content: str
    citations: list[Citation]
    stats: ChatStats
    mode: AnalysisMode
    timestamp: datetime
    # Populated when the message routed to the full-coverage strategy brief.
    strategy: dict | None = None
    # Populated when the message routed to the exhaustive authority mapper:
    # the audit runs as a background job the client polls via /jobs/{job_id}.
    authority_map_job: dict | None = None
    # Persisted chat session this exchange was appended to (None if persistence
    # failed — persistence is best-effort and never blocks the response).
    session_id: str | None = None


# Persistent Chat Session Models
class CreateChatSessionRequest(BaseModel):
    """Create a new persisted chat session."""

    title: str = Field(..., min_length=1, max_length=255)
    # Optional matter to file the session under (caller must be a member).
    # Omitted -> the caller's personal (owner-only) scope.
    matter_id: str | None = Field(None, max_length=36)


class ChatSessionSummary(BaseModel):
    """Session list item for the History panel."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


# ---- Matters (collaboration / sharing) ----


class CreateMatterRequest(BaseModel):
    """Create a shared matter."""

    name: str = Field(..., min_length=1, max_length=300)
    client_name: str | None = Field(None, max_length=300)


class AddMatterMemberRequest(BaseModel):
    """Invite a colleague to a matter by email."""

    email: str = Field(..., min_length=3, max_length=255)


class MatterMemberResponse(BaseModel):
    user_id: str
    email: str | None = None
    name: str | None = None
    role: str


class MatterResponse(BaseModel):
    id: str
    name: str
    client_name: str | None = None
    is_personal: bool
    owner_id: str
    role: str  # the caller's role in this matter: "owner" | "member"
    member_count: int
    created_at: datetime


class MatterListResponse(BaseModel):
    matters: list[MatterResponse]


class MatterDetailResponse(MatterResponse):
    members: list[MatterMemberResponse]


class ChatSessionMessage(BaseModel):
    """A persisted message within a chat session thread."""

    id: str
    role: str  # 'user' | 'assistant'
    content: str
    citations: list[dict] = []
    strategy: dict | None = None
    stats: dict | None = None
    created_at: datetime


class ChatSessionDetail(BaseModel):
    """Full session thread: metadata plus ordered messages."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatSessionMessage]


class ChatSessionListResponse(BaseModel):
    """Sessions for the current user, newest first."""

    sessions: list[ChatSessionSummary]


# Document Models


class Document(BaseModel):
    id: str
    user_id: str  # Owner - tenant isolation
    # Matter this document belongs to. None == owner's personal scope (visible
    # only to the owner), which is the historical per-user behavior. When set to
    # a shared matter, every member of that matter can access the document.
    matter_id: str | None = None
    filename: str
    content_type: str
    size: int
    source: ConnectorType
    source_id: str | None = None  # ID in the source system
    status: DocumentStatus
    chunk_count: int = 0
    created_at: datetime
    indexed_at: datetime | None = None
    metadata: dict[str, Any] = {}
    folder_path: str | None = None  # Full folder path (e.g., "/Cases/Smith v Jones/")


class DocumentList(BaseModel):
    documents: list[Document]
    count: int


# Connector Models
class ConnectorStatus(BaseModel):
    type: ConnectorType
    connected: bool
    configured: bool = True
    account_name: str | None = None
    account_email: str | None = None
    docs_indexed: int = 0
    last_sync: datetime | None = None


class ConnectorAuthUrl(BaseModel):
    auth_url: str
    state: str


class SyncStatus(BaseModel):
    connector: ConnectorType
    status: str  # "idle", "syncing", "completed", "failed"
    progress: float = 0.0
    docs_processed: int = 0
    docs_total: int = 0
    current_file: str | None = None
    error: str | None = None


# RAG Settings Models
class RAGSettings(BaseModel):
    """RAG configuration settings with validation."""

    vector_db: str = Field(default="chroma", pattern=r"^(chroma|pinecone)$")
    index_name: str = Field(default="casecite-legal-docs", min_length=1, max_length=100)
    embedding_model: str = Field(default="text-embedding-3-small", max_length=100)
    dimensions: int = Field(default=1536, ge=256, le=4096)
    chunk_size: int = Field(default=512, ge=100, le=2000)
    chunk_overlap: int = Field(default=128, ge=0, le=500)
    # Same default as settings.similarity_threshold. With text-embedding-3-* a
    # relevant chunk scores ~0.30-0.50, so the old 0.55 default put every real
    # match below the floor for users who had never saved their settings.
    similarity_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    top_k: int = Field(default=10, ge=1, le=100)
    # Cross-encoder reranking. Effective only when the optional
    # sentence-transformers package is installed on the server; otherwise the
    # toggle is ignored and results keep their similarity / keyword order.
    enable_reranking: bool = True
    # Blend a BM25 keyword score over the vector-search candidates into the
    # ranking (rescoring, not a separate keyword index).
    hybrid_search: bool = True
    # Flag which retrieved passages the answer actually draws on. Does not
    # approve citations — review status stays with the reviewer.
    citation_verification: bool = True
    context_compression: bool = False
    query_expansion: bool = True
    source_tracking: bool = True
    llm_model: str = Field(default="gpt-5.5", max_length=100)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=100, le=128000)
    # Firm contract playbook: standing review standards applied to every
    # contract analysis/redline (who we usually represent, what we never
    # accept, preferred fallback positions).
    contract_playbook: str | None = Field(None, max_length=20000)
    # Practice profile: NOTHING about a practice is baked into the product.
    # The user states their practice area, a profile of what matters in that
    # practice is generated on their behalf, they edit it, and it rides along
    # with every review/redline/draft as standing context.
    practice_area: str | None = Field(None, max_length=200)
    practice_profile: str | None = Field(None, max_length=20000)
    # Custom prompts - if empty/None, uses defaults
    custom_system_prompt: str | None = Field(None, max_length=50000)
    custom_grounding_rules: str | None = Field(None, max_length=10000)
    # Factual query prompt - for quick/concise answers
    custom_factual_prompt: str | None = Field(None, max_length=10000)
    # Mode-specific prompts - customize each analysis mode
    custom_research_prompt: str | None = Field(None, max_length=10000)
    custom_case_prompt: str | None = Field(None, max_length=10000)
    custom_document_prompt: str | None = Field(None, max_length=10000)
    custom_compliance_prompt: str | None = Field(None, max_length=10000)
    custom_strategy_prompt: str | None = Field(None, max_length=10000)

    @model_validator(mode="after")
    def validate_overlap_less_than_chunk(self):
        """Ensure overlap is less than chunk size."""
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"Chunk overlap ({self.chunk_overlap}) must be less than chunk size ({self.chunk_size})"
            )
        return self


# Document Tree Models (for folder/file selection UI)
class DocumentTreeItem(BaseModel):
    """Represents a file or folder in the document tree."""

    id: str  # Document ID for files, folder path for folders
    name: str
    type: str  # "file" or "folder"
    path: str  # Full path (e.g., "/Cases/Smith v Jones/brief.pdf")
    source: ConnectorType | None = None  # Source connector
    doc_type: str | None = None  # Document type for files
    size: int | None = None  # File size
    children: list["DocumentTreeItem"] = []  # Child items for folders
    document_count: int = 0  # Number of documents in folder (including subfolders)


# Enable forward reference resolution
DocumentTreeItem.model_rebuild()


class DocumentTreeResponse(BaseModel):
    """Response containing the full document tree."""

    tree: list[DocumentTreeItem]
    total_documents: int
    total_folders: int
    sources: list[str]  # Available sources (google_drive, onedrive, local, etc.)


# =============================================================================
# Auth Request Models
# =============================================================================


class DemoLoginRequest(BaseModel):
    """Request body for the DEBUG-only dev login (POST /auth/demo/login)."""

    email: str = ""  # Defaults to routers.auth.DEV_ACCOUNT_EMAIL at runtime
    password: str = "demo"


class AzureLoginRequest(BaseModel):
    """Request body for Azure AD login."""

    token: str  # Azure AD access token


class EmailLoginRequest(BaseModel):
    """Request body for email/password login."""

    email: str
    password: str


class RegisterRequest(BaseModel):
    """Request body for self-hosted user registration."""

    email: EmailStr
    name: str
    password: str
    company: str | None = None
    # Required only for bootstrapping the first (admin) account when the operator
    # has set REGISTRATION_BOOTSTRAP_TOKEN. Ignored for subsequent registrations.
    bootstrap_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    """Request body for forgot password."""

    email: str


class ResetPasswordRequest(BaseModel):
    """Request body for password reset."""

    token: str
    new_password: str


class VerifyResetTokenRequest(BaseModel):
    """Request body for verifying a reset token."""

    token: str


class ChangePasswordRequest(BaseModel):
    """Request body for an authenticated self-service password change."""

    current_password: str
    new_password: str


# =============================================================================
# Admin User Management
# =============================================================================
class AdminUserItem(BaseModel):
    """A user account as shown in the admin Users tab."""

    id: str
    email: str
    name: str
    roles: list[str]
    is_active: bool
    mfa_enabled: bool = False
    must_change_password: bool = False
    created_at: datetime | None = None
    last_login: datetime | None = None


class AdminUserListResponse(BaseModel):
    """List of all user accounts."""

    users: list[AdminUserItem]


class InviteUserRequest(BaseModel):
    """Request body for inviting (creating) a user with an assigned role."""

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(..., min_length=1, max_length=40)


class InviteUserResponse(BaseModel):
    """Response after creating an invited user. Returns a one-time temp password."""

    user: AdminUserItem
    temporary_password: str


class UpdateUserRoleRequest(BaseModel):
    """Request body for changing a user's role."""

    role: str = Field(..., min_length=1, max_length=40)


class UpdateRolePermissionsRequest(BaseModel):
    """Request body for setting the permission list of one role."""

    permissions: list[str] = Field(..., max_length=100)


class WorkspaceSessionCreate(BaseModel):
    """Create a restorable workspace-session snapshot."""

    surface: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=300)
    payload: dict = Field(default_factory=dict)


class WorkspaceSessionUpdate(BaseModel):
    """Update a workspace-session snapshot (partial)."""

    title: str | None = Field(None, min_length=1, max_length=300)
    payload: dict | None = None


class SetUserActiveRequest(BaseModel):
    """Request body for activating or deactivating (offboarding) a user."""

    is_active: bool


# =============================================================================
# MFA (TOTP)
# =============================================================================


class MfaSetupResponse(BaseModel):
    """Enrollment data: show the QR (from provisioning_uri) and/or the secret."""

    secret: str
    provisioning_uri: str


class MfaEnableRequest(BaseModel):
    """Confirm enrollment by proving possession of the authenticator."""

    code: str = Field(..., min_length=6, max_length=10)


class MfaEnableResponse(BaseModel):
    """One-time recovery codes — shown once, stored only as hashes."""

    recovery_codes: list[str]


class MfaDisableRequest(BaseModel):
    """Disable MFA by proving a current TOTP (or recovery) code AND the password.

    ``password`` is required for accounts that have a local password, so a
    hijacked session alone cannot strip the second factor. SSO-only accounts
    (no local password) omit it.
    """

    code: str = Field(..., min_length=6, max_length=20)
    password: str | None = Field(default=None, max_length=1024)


class MfaVerifyRequest(BaseModel):
    """Second login step: exchange challenge + code for tokens."""

    mfa_token: str
    code: str = Field(..., min_length=6, max_length=20)


class MfaStatusResponse(BaseModel):
    enabled: bool
    recovery_codes_remaining: int = 0


class AuditLogListResponse(BaseModel):
    """Admin audit-trail query result (raw structured entries)."""

    logs: list[dict]
    count: int


class AuditVerifyResponse(BaseModel):
    """Result of verifying the audit trail's HMAC hash chain."""

    valid: bool
    entries_checked: int
    first_invalid_id: str | None = None
    reason: str | None = None
    # Entries written before chain linkage was enforced (signature checked only)
    legacy_entries: int = 0
    # True when the range held more entries than one verification scans
    truncated: bool = False


# =============================================================================
# Branding Models (moved from routers/branding.py)
# =============================================================================


class BrandingResponse(BaseModel):
    """Public branding configuration returned to the frontend."""

    firm_name: str
    logo_url: str | None = None
    primary_color: str
    secondary_color: str
    accent_color: str
    favicon_url: str | None = None
    custom_css: str | None = None
    updated_at: str | None = None


class BrandingUpdate(BaseModel):
    """Request body for updating branding configuration."""

    firm_name: str | None = Field(None, max_length=255, description="Firm / product display name")
    logo_url: str | None = Field(None, max_length=500, description="URL of the logo image")
    primary_color: str | None = Field(None, max_length=20, description="Primary brand color (hex)")
    secondary_color: str | None = Field(
        None, max_length=20, description="Secondary brand color (hex)"
    )
    accent_color: str | None = Field(None, max_length=20, description="Accent color (hex)")
    favicon_url: str | None = Field(None, max_length=500, description="URL of the favicon")
    custom_css: str | None = Field(
        None, max_length=50_000, description="Additional CSS injected into the frontend"
    )

    @field_validator("logo_url", "favicon_url")
    @classmethod
    def _safe_image_url(cls, v: str | None) -> str | None:
        """Same-origin path or https URL only ("" clears the value).

        These land in <img src> / <link href> on the public login page, so
        javascript:, data: and plain-http URLs are refused.
        """
        if not v:
            return v
        v = v.strip()
        same_origin = v.startswith("/") and not v.startswith("//") and "\\" not in v
        if not (same_origin or v.lower().startswith("https://")):
            raise ValueError("must be an https:// URL or a path starting with /")
        if any(ch.isspace() or ch in "\"'<>" for ch in v):
            raise ValueError("contains characters that are not allowed in a URL")
        return v

    @field_validator("primary_color", "secondary_color", "accent_color")
    @classmethod
    def _hex_color(cls, v: str | None) -> str | None:
        """Hex colours only — the value is interpolated into CSS."""
        if v is None:
            return v
        v = v.strip()
        if not re.fullmatch(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", v):
            raise ValueError("must be a hex colour such as #1A2B3C")
        return v


# =============================================================================
# Contract Analysis Request Models (moved from routers/contract_analysis.py)
# =============================================================================


class FullAnalyzeRequest(BaseModel):
    document_text: str | None = Field(
        None, description="Full contract text; omit when document_id is given", max_length=2_000_000
    )
    contract_type: str | None = Field(
        "auto", description='Contract type slug, or "auto"/empty to auto-detect'
    )
    jurisdiction: str | None = None
    effective_date: str | None = Field(
        None, description="ISO date — used to resolve relative deadlines"
    )
    document_id: str | None = None
    representing: str | None = Field(
        None,
        description='Free-text description of the client\'s side (e.g. "Customer", '
        '"Vendor"). Omit for a neutral analysis.',
    )
    posture: str = Field(
        "balanced", description='"strict" (flag everything, aggressive fallbacks) or "balanced"'
    )


class ContractChatRequest(BaseModel):
    document_id: str | None = Field(
        None,
        description="Indexed document to chat about. Optional for mode='draft' — "
        "drafting from scratch needs no reference document.",
    )
    draft_text: str | None = Field(
        None,
        max_length=500_000,
        description="The drafting workspace's current draft. With mode='draft' the "
        "message revises it; other modes answer questions about it.",
    )
    reference_document_ids: list[str] | None = Field(
        None,
        max_length=4,
        description="Indexed documents attached as drafting source material — "
        '"write a demand letter based on this service agreement".',
    )
    message: str = Field(..., min_length=1, max_length=8000)
    mode: str | None = Field(
        None,
        description='Explicit mode ("ask"|"analyze"|"redline"|"draft"). The '
        "user selected it and their message IS the instructions — no intent "
        "routing, no guessing. Omit for automatic routing.",
    )


class DraftPlanRequest(BaseModel):
    """Phase 1 of a long draft: plan the sections from the full reference bundle."""

    message: str = Field(..., min_length=1, max_length=8000)
    reference_document_ids: list[str] | None = Field(None, max_length=4)
    target_pages: int = Field(
        ..., ge=1, le=200, description="Approximate length of the finished document in pages"
    )


class DraftGenerateRequest(BaseModel):
    """Phases 2-3 of a long draft: draft every planned section, then reconcile."""

    message: str = Field(..., min_length=1, max_length=8000)
    reference_document_ids: list[str] | None = Field(None, max_length=4)
    plan: dict = Field(..., description="The plan from /draft/plan, as edited by the user")

    @field_validator("plan")
    @classmethod
    def _bounded_plan(cls, v: dict) -> dict:
        """A plan is a section outline, not a document — cap what gets queued."""
        import json

        if len(json.dumps(v, default=str)) > 200_000:
            raise ValueError("plan is too large")
        return v


class PracticeProfileRequest(BaseModel):
    practice_area: str = Field(..., min_length=2, max_length=200)


class CompareRequest(BaseModel):
    # New multi-document form: 2-4 indexed documents, first is the baseline.
    document_ids: list[str] | None = Field(
        None, min_length=2, max_length=4, description="2-4 indexed documents; first is baseline"
    )
    # Legacy pairwise form (kept for compatibility).
    document_id_a: str | None = Field(None, description="Baseline contract (indexed document)")
    document_id_b: str | None = Field(None, description="Contract to compare against the baseline")
    focus: str | None = Field(
        None, max_length=2000, description="The user's own comparison instructions"
    )


class DraftExportRequest(BaseModel):
    title: str = Field("Draft", max_length=300)
    text: str = Field(..., min_length=1, max_length=500_000)


class RedlineExportRequest(BaseModel):
    """POST body for redline export: rejected refs plus the user's own edits
    to proposed text (ref -> replacement wording)."""

    exclude: list[str] = Field(default_factory=list, max_length=2000)
    overrides: dict[str, str] = Field(default_factory=dict, max_length=2000)

    @field_validator("overrides")
    @classmethod
    def _bounded_overrides(cls, v: dict[str, str]) -> dict[str, str]:
        if any(len(k) > 200 or len(text) > 100_000 for k, text in v.items()):
            raise ValueError("an override is too large")
        return v


# =============================================================================
# File Picker Models (moved from routers/pickers.py)
# =============================================================================


class PickerConfig(BaseModel):
    """Configuration for client-side file pickers."""

    google_enabled: bool = False
    google_api_key: str | None = None
    google_client_id: str | None = None
    google_app_id: str | None = None

    microsoft_enabled: bool = False
    microsoft_client_id: str | None = None
    microsoft_tenant_id: str | None = None

    box_enabled: bool = False
    box_client_id: str | None = None

    dropbox_enabled: bool = False
    dropbox_app_key: str | None = None


class GooglePickerFile(BaseModel):
    """File selected from Google Picker."""

    id: str
    name: str
    mimeType: str
    url: str | None = None
    sizeBytes: int | None = None
    # OAuth token from picker (scoped to selected files only)
    oauthToken: str


class OneDrivePickerFile(BaseModel):
    """File selected from OneDrive/SharePoint Picker (v8)."""

    id: str
    name: str
    size: int | None = None
    webUrl: str | None = None
    # Direct download URL provided by picker
    downloadUrl: str | None = None
    # Access token from picker (scoped to selected files)
    accessToken: str
    # v8 picker fields for cross-drive (SharePoint) file access
    driveId: str | None = None
    sharepointEndpoint: str | None = None


class BoxPickerFile(BaseModel):
    """File selected from Box Content Picker."""

    id: str
    name: str
    size: int | None = None
    # Access token from Box UI Elements
    accessToken: str


class DropboxChooserFile(BaseModel):
    """File selected from Dropbox Chooser."""

    name: str
    link: str  # Direct download link (temporary, valid for 4 hours)
    bytes: int | None = None
    icon: str | None = None


class BoxPickerTokenResponse(BaseModel):
    """Downscoped Box token for the browser-side Content Picker."""

    access_token: str
    expires_in: int


class PickerImportResponse(BaseModel):
    """Response from file import."""

    imported: int
    failed: int
    errors: list[str]
