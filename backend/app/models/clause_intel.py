"""Clause intelligence models — taxonomy, jurisdiction rules, contract types, deviations."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.base import Base


class ClauseCanonical(Base):
    """
    Canonical clause type in the taxonomy.

    Each row is a distinct clause type (indemnification, limitation_of_liability, etc.)
    with its required sub-elements and a market-standard reference body.
    """

    __tablename__ = "clause_canonicals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(80), nullable=False, unique=True)  # e.g. "limitation_of_liability"
    name = Column(String(200), nullable=False)
    category = Column(String(80), nullable=False)  # liability, ip, term, dispute, payment, etc.
    description = Column(Text, nullable=True)

    # Required sub-elements (JSON list of {key, name, description, required: bool})
    sub_elements = Column(JSON, nullable=False, default=list)

    # Market-standard reference text used as deviation baseline
    market_standard_text = Column(Text, nullable=False)

    # Embedding cached as JSON list[float]; populated on seed/update
    embedding = Column(JSON, nullable=True)
    embedding_model = Column(String(80), nullable=True)

    # Regex anchors (list[str]) — high-confidence indicators of this clause type
    regex_anchors = Column(JSON, nullable=False, default=list)

    # Required keywords (list[str]) — must appear for partial-match floor
    required_keywords = Column(JSON, nullable=False, default=list)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    rules = relationship(
        "ClauseJurisdictionRule", back_populates="canonical", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_clause_canonical_category", "category"),)


class ClauseJurisdictionRule(Base):
    """
    Per-jurisdiction enforceability rule for a canonical clause.

    Stored as structured rules, not prose — frontends/services compose
    user-facing prose from the structured fields.
    """

    __tablename__ = "clause_jurisdiction_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canonical_id = Column(
        Integer, ForeignKey("clause_canonicals.id", ondelete="CASCADE"), nullable=False
    )
    jurisdiction = Column(String(40), nullable=False)  # "CA", "TX", "NY", "DE", "US-FED"

    # Enforceability: enforceable | limited | void | reformable | unsettled
    enforceability = Column(String(40), nullable=False)

    # Structured constraints — what's required/banned in this jurisdiction
    # e.g. {"max_duration_months": 12, "geographic_scope": "reasonable",
    #       "consideration_required": true, "blue_pencil_allowed": true}
    constraints = Column(JSON, nullable=False, default=dict)

    # Authority — statute(s) and case(s) that establish the rule
    # [{"type": "statute", "cite": "Cal. Bus. & Prof. Code § 16600"}, ...]
    authorities = Column(JSON, nullable=False, default=list)

    # Short note (one sentence) used in user-facing summaries
    note = Column(Text, nullable=True)

    # Recommended replacement language for invalid clauses in this jurisdiction
    recommended_text = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    canonical = relationship("ClauseCanonical", back_populates="rules")

    __table_args__ = (
        UniqueConstraint("canonical_id", "jurisdiction", name="uq_clause_juris_rule"),
        Index("idx_clause_juris", "jurisdiction"),
    )


class ContractTypeRequirement(Base):
    """
    Required and recommended clauses for a given contract type.

    Used by the missing-clause detector.
    """

    __tablename__ = "contract_type_requirements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contract_type = Column(String(80), nullable=False)  # nda, msa, employment, sow, license
    canonical_slug = Column(String(80), nullable=False)
    requirement = Column(String(20), nullable=False)  # required | recommended | optional
    rationale = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("contract_type", "canonical_slug", name="uq_contract_type_req"),
        Index("idx_contract_type", "contract_type"),
    )


class ClauseDeviationFinding(Base):
    """
    Persisted deviation finding from a contract analysis run.

    Each row is one specific deviation between a tagged clause and its
    canonical market-standard counterpart.
    """

    __tablename__ = "clause_deviations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(String(64), nullable=False, index=True)
    canonical_id = Column(
        Integer, ForeignKey("clause_canonicals.id", ondelete="SET NULL"), nullable=True
    )
    canonical_slug = Column(String(80), nullable=False)

    # Where in the contract the clause was found
    span_start = Column(Integer, nullable=True)
    span_end = Column(Integer, nullable=True)
    matched_text = Column(Text, nullable=False)

    # Deviation category: missing_subelement | weakened | strengthened | reversed |
    #                     scope_change | cap_change | mutual_to_unilateral
    deviation_type = Column(String(40), nullable=False)
    sub_element = Column(String(80), nullable=True)
    severity = Column(String(20), nullable=False)  # critical | major | minor | informational

    # Structured detail of the deviation
    detail = Column(JSON, nullable=False, default=dict)

    # Confidence the classifier had on the underlying tag (0..1)
    classifier_confidence = Column(Float, nullable=True)

    # Optional LLM-generated explanation (only for explanation, not detection)
    explanation = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("idx_clause_dev_analysis", "analysis_id"),)


class ClauseTagFinding(Base):
    """
    Persisted result of the classifier — every clause it tagged in a contract.
    """

    __tablename__ = "clause_tag_findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(String(64), nullable=False, index=True)
    canonical_id = Column(
        Integer, ForeignKey("clause_canonicals.id", ondelete="SET NULL"), nullable=True
    )
    canonical_slug = Column(String(80), nullable=False)

    span_start = Column(Integer, nullable=False)
    span_end = Column(Integer, nullable=False)
    matched_text = Column(Text, nullable=False)

    # How the tag was made: embedding | regex | hybrid
    method = Column(String(20), nullable=False)
    confidence = Column(Float, nullable=False)

    # Detected sub-elements (list[str]) — keys from canonical.sub_elements present in matched_text
    detected_sub_elements = Column(JSON, nullable=False, default=list)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ContractAnalysisRun(Base):
    """
    Top-level record of one contract analysis (Phase 1 + future phases).

    Holds the contract type, jurisdiction, summary metrics, and acts as
    parent for tag findings, deviations, and (Phase 2) obligations/risk.
    """

    __tablename__ = "contract_analysis_runs"

    id = Column(String(64), primary_key=True)  # uuid hex
    user_id = Column(String(64), nullable=True, index=True)
    # Matter this run belongs to. None == owner's personal scope; a shared matter
    # makes it visible to that matter's members. See app/services/matters.py.
    matter_id = Column(String(36), nullable=True, index=True)
    document_id = Column(String(64), nullable=True, index=True)
    contract_type = Column(String(80), nullable=False)
    jurisdiction = Column(String(40), nullable=True)

    document_length_chars = Column(Integer, nullable=False)
    tags_found = Column(Integer, nullable=False, default=0)
    deviations_found = Column(Integer, nullable=False, default=0)
    missing_required = Column(Integer, nullable=False, default=0)

    # Free-form metadata snapshot
    summary = Column(JSON, nullable=False, default=dict)

    is_complete = Column(Boolean, nullable=False, default=False)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
