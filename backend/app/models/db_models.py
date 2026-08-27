"""
SQLAlchemy ORM Models — backwards-compatibility re-exports.

Models are split by domain into separate files within this package.
This file re-exports everything so existing imports continue to work.
"""

# Base
# Audit
from app.models.audit import AuditLog  # noqa: F401

# Auth
from app.models.auth import User  # noqa: F401
from app.models.base import Base  # noqa: F401

# Chat Sessions (persistent Matter Strategy conversations)
from app.models.chat_sessions import ChatMessageDB, ChatSessionDB  # noqa: F401

# Clause Intelligence (Phase 1)
from app.models.clause_intel import (  # noqa: F401
    ClauseCanonical,
    ClauseDeviationFinding,
    ClauseJurisdictionRule,
    ClauseTagFinding,
    ContractAnalysisRun,
    ContractTypeRequirement,
)

# Contract Analysis (Phase 2)
from app.models.contract_analysis import (  # noqa: F401
    ContractDeadline,
    ContractDefinedTerm,
    ContractObligation,
    ContractParty,
)

# Enums
from app.models.enums import (  # noqa: F401
    DocumentStatus,
    UserRole,
)

# Matters & membership (collaboration/isolation unit)
from app.models.matters import Matter, MatterMember  # noqa: F401

# Branding, Instance Secrets, Workspace Sessions
from app.models.tracking import (  # noqa: F401
    BrandingConfigDB,
    InstanceSecretDB,
    WorkspaceSessionDB,
)
