"""Response models barrel — re-exports all response models for the API."""

# Auth
from app.models.responses.auth import (
    AzureConfigResponse,
    CurrentUserResponse,
    LoginResponse,
    ResetTokenValidationResponse,
    SessionsResponse,
    TokenRefreshResponse,
    UserInfo,
)

# Branding
from app.models.responses.branding import (
    BrandingLogoResponse,
)
from app.models.responses.common import (
    DeletedResponse,
    MessageResponse,
    StatusResponse,
)

# Connectors
from app.models.responses.connectors import (
    ConnectorCallbackResponse,
    ConnectorListResponse,
    SyncStartResponse,
    SyncStatusResponse,
)

# Documents
from app.models.responses.documents import (
    DocumentContentResponse,
    DocumentDeleteResponse,
)

# Jobs
from app.models.responses.jobs import (
    JobCancelledResponse,
    JobListResponse,
    JobStatusResponse,
)

# Judge Intel
from app.models.responses.judge_intel import (
    JudgeBuildResponse,
    JudgeDeleteResponse,
    JudgeMetricsResponse,
    JudgeOpinionsResponse,
    JudgeOpinionTextResponse,
    JudgeProfileResponse,
    JudgeSearchResponse,
    JudgeStatsResponse,
)

# Settings
from app.models.responses.settings import (
    ClearResponse,
    ModePrompts,
    PromptDefaultsResponse,
)

# System
from app.models.responses.system import (
    HealthResponse,
    MetricsResponse,
    ReadyResponse,
    SystemRootResponse,
)

# Tools
from app.models.responses.tools import (
    DocketListResponse,
    OralArgumentListResponse,
    PrecedentListResponse,
)

# User Keys
from app.models.responses.user_keys import (
    KeyMaskedResponse,
    KeySaveResponse,
)

__all__ = [
    "StatusResponse",
    "MessageResponse",
    "DeletedResponse",
    "UserInfo",
    "LoginResponse",
    "TokenRefreshResponse",
    "SessionsResponse",
    "CurrentUserResponse",
    "AzureConfigResponse",
    "ResetTokenValidationResponse",
    "ContractAnalysisResponse",
    "PleadingAnalysisResponse",
    "QuickScanResponse",
    "AnalysisHistoryResponse",
    "JobStatusResponse",
    "JobCancelledResponse",
    "JobListResponse",
    "JudgeSearchResponse",
    "JudgeBuildResponse",
    "JudgeProfileResponse",
    "JudgeOpinionsResponse",
    "JudgeOpinionTextResponse",
    "JudgeStatsResponse",
    "JudgeMetricsResponse",
    "JudgeDeleteResponse",
    "ConnectorListResponse",
    "ConnectorCallbackResponse",
    "SyncStartResponse",
    "SyncStatusResponse",
    "ModePrompts",
    "PromptDefaultsResponse",
    "ClearResponse",
    "SystemRootResponse",
    "HealthResponse",
    "ReadyResponse",
    "MetricsResponse",
    "DocumentContentResponse",
    "DocumentDeleteResponse",
    "PrecedentListResponse",
    "DocketListResponse",
    "OralArgumentListResponse",
    "BrandingLogoResponse",
    "KeySaveResponse",
    "KeyMaskedResponse",
]
