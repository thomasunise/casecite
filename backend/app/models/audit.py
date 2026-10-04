"""Audit logging models."""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from app.models.base import Base


def _utcnow_naive() -> datetime:
    """Current UTC time without tzinfo, matching the naive `timestamp` column."""
    return datetime.now(UTC).replace(tzinfo=None)


class AuditLog(Base):
    """Queryable mirror of the audit trail; the signed JSONL files are the record.

    `timestamp` is a naive DateTime holding UTC.
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=_utcnow_naive, nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)

    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_email = Column(String(255), nullable=True)

    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(255), nullable=True)
    action_details = Column(JSON, nullable=True)

    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    environment = Column(String(50), nullable=True)

    entry_hash = Column(String(64), nullable=True)
    previous_hash = Column(String(64), nullable=True)
    correlation_id = Column(String(36), nullable=True)

    __table_args__ = (
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_timestamp_type", "timestamp", "event_type"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )
