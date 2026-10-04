"""
Contract analysis models — obligations, parties, deadlines, risk, defined terms.

These rows are owned by a `contract_analysis_runs.id` (declared in Phase 1).
The Phase 1 ContractAnalysisRun is shared as the parent record.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from app.models.base import Base


class ContractParty(Base):
    """
    A canonical party in a contract.

    Aliases (e.g., 'Licensor', 'the Company', 'ABC Inc.') are resolved to a
    single canonical party with role and observed surface forms stored.
    """

    __tablename__ = "contract_parties"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(String(64), nullable=False, index=True)

    # Display name — usually the formal entity name, fallback to first observed alias
    canonical_name = Column(String(300), nullable=False)

    # Role: counterparty | provider | customer | licensor | licensee | indemnitor | indemnitee | other
    role = Column(String(40), nullable=True)

    # Observed surface forms (list[str])
    aliases = Column(JSON, nullable=False, default=list)

    # First-seen offset
    first_span_start = Column(Integer, nullable=True)
    first_span_end = Column(Integer, nullable=True)

    detection_method = Column(String(20), nullable=False)  # defined | header | heuristic
    confidence = Column(Float, nullable=False, default=1.0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ContractObligation(Base):
    """
    A structured obligation extracted from the contract.

    Fields are populated either by the local rule extractor (regex/NLP) or
    a strict-schema LLM call. Validation is enforced in code, not by the LLM.
    """

    __tablename__ = "contract_obligations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(String(64), nullable=False, index=True)

    # Subject — the obligated party (canonical_name) — may be unresolved (None)
    subject_party = Column(String(300), nullable=True)
    subject_party_id = Column(
        Integer, ForeignKey("contract_parties.id", ondelete="SET NULL"), nullable=True
    )

    # Modal verb: shall | must | will | agrees_to | may | should
    modal = Column(String(20), nullable=False)

    # Verb / action — short normalized phrase
    action = Column(String(400), nullable=False)

    # Object of action (free text)
    object_text = Column(Text, nullable=True)

    # Conditions — list[str] of preconditions/triggers ("upon notice", "if Customer requests")
    conditions = Column(JSON, nullable=False, default=list)

    # Time anchors — list of structured deadline records used by deadline pipeline
    deadlines = Column(JSON, nullable=False, default=list)

    # Source span
    span_start = Column(Integer, nullable=False)
    span_end = Column(Integer, nullable=False)
    matched_text = Column(Text, nullable=False)

    # Category: payment | delivery | notice | compliance | confidentiality |
    #           ip | termination | warranty | indemnity | reporting | other
    category = Column(String(40), nullable=True)

    # Risk-relevance flags
    is_unilateral = Column(Integer, nullable=False, default=0)  # 0/1 boolean
    is_perpetual = Column(Integer, nullable=False, default=0)
    is_continuing = Column(Integer, nullable=False, default=0)

    detection_method = Column(String(20), nullable=False)  # rule | llm | hybrid
    confidence = Column(Float, nullable=False, default=1.0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ContractDeadline(Base):
    """
    A specific date / period extracted from the contract.

    `resolved_date` is populated when an effective date is supplied;
    otherwise only the relative description is stored.
    """

    __tablename__ = "contract_deadlines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(String(64), nullable=False, index=True)
    obligation_id = Column(
        Integer, ForeignKey("contract_obligations.id", ondelete="SET NULL"), nullable=True
    )

    # Kind: absolute | relative_offset | period | recurring | conditional
    kind = Column(String(20), nullable=False)

    # Free-text description as it appeared
    description = Column(String(400), nullable=False)

    # Anchor: effective_date | invoice_date | termination | notice | other
    anchor = Column(String(40), nullable=True)

    # Offset in days (positive=after, negative=before). NULL when absolute.
    offset_days = Column(Integer, nullable=True)

    # Period in days (for recurring/duration). NULL when not applicable.
    period_days = Column(Integer, nullable=True)

    # Resolved absolute date (only if effective_date supplied to analyzer)
    resolved_date = Column(DateTime, nullable=True)

    span_start = Column(Integer, nullable=True)
    span_end = Column(Integer, nullable=True)
    matched_text = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ContractDefinedTerm(Base):
    """A defined term ('Confidential Information' = ...) and its usage stats."""

    __tablename__ = "contract_defined_terms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(String(64), nullable=False, index=True)

    term = Column(String(200), nullable=False)
    definition_text = Column(Text, nullable=True)

    defined = Column(Integer, nullable=False, default=1)  # 0 if used but never defined
    usage_count = Column(Integer, nullable=False, default=0)

    # Findings flags
    used_but_undefined = Column(Integer, nullable=False, default=0)
    defined_but_unused = Column(Integer, nullable=False, default=0)
    circular_reference = Column(Integer, nullable=False, default=0)

    span_start = Column(Integer, nullable=True)
    span_end = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# Add an index on the run table from the contract analysis side
Index("idx_contract_obligations_analysis", ContractObligation.analysis_id)
Index("idx_contract_deadlines_analysis", ContractDeadline.analysis_id)
Index("idx_contract_defined_analysis", ContractDefinedTerm.analysis_id)
