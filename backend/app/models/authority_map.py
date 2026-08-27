"""
Authority Mapper models.

Maps legal propositions found in an uploaded document to supporting case-law
authorities. Every supporting passage is *verbatim-verified* against the source
text — a quote that cannot be located in the real source is flagged unverified
rather than presented as fact. This is the anti-hallucination guarantee.
"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Float, Index, Integer, String, Text

from app.models.base import Base


class AuthorityMapRun(Base):
    """Parent record for one authority-mapping pass over a document."""

    __tablename__ = "authority_map_runs"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=True, index=True)
    # Matter this run belongs to. None == owner's personal scope; a shared matter
    # makes it visible to that matter's members. See app/services/matters.py.
    matter_id = Column(String(36), nullable=True, index=True)
    document_id = Column(String(64), nullable=True, index=True)
    document_name = Column(String(300), nullable=True)
    document_length_chars = Column(Integer, nullable=False, default=0)
    jurisdiction = Column(String(20), nullable=True)

    propositions_found = Column(Integer, nullable=False, default=0)
    authorities_found = Column(Integer, nullable=False, default=0)
    verified_count = Column(Integer, nullable=False, default=0)

    summary = Column(JSON, nullable=False, default=dict)
    is_complete = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class AuthorityMapping(Base):
    """One (proposition -> supporting authority) edge with anchor offsets."""

    __tablename__ = "authority_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, index=True)

    # The legal proposition extracted from the user's document
    proposition = Column(Text, nullable=False)
    # Verbatim quote from the user's document, with offsets for in-doc highlight
    doc_quote = Column(Text, nullable=True)
    doc_span_start = Column(Integer, nullable=True)
    doc_span_end = Column(Integer, nullable=True)

    # Source of the authority: courtlistener ("user_corpus" only in legacy rows —
    # the user's own files are no longer searched for authority)
    source = Column(String(20), nullable=False)

    # Authority identity
    case_name = Column(String(400), nullable=True)
    citation = Column(String(200), nullable=True)
    # CourtListener opinion id (as string) OR user document id
    source_ref = Column(String(64), nullable=True)
    source_url = Column(String(500), nullable=True)

    # The supporting passage from the source authority
    support_quote = Column(Text, nullable=True)
    # Char offsets of support_quote within the source text (for click-to-anchor)
    source_span_start = Column(Integer, nullable=True)
    source_span_end = Column(Integer, nullable=True)

    # Verified == True only when support_quote was located verbatim in source text
    verified = Column(Integer, nullable=False, default=0)
    relevance = Column(Float, nullable=False, default=0.0)
    note = Column(Text, nullable=True)

    # Explicit reasoning for WHY this authority supports the proposition:
    # {"steps": [{"type","description","evidence"}...], "application": "..."}
    # Shown as the reasoning chain / logic tree in the citation modal.
    reasoning = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index("idx_authority_mappings_run", AuthorityMapping.run_id)
