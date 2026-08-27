"""Workspace sessions, branding, and instance-secret models."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from app.models.base import Base


class WorkspaceSessionDB(Base):
    """A restorable snapshot of one surface's working session.

    Universal History: contracts conversations (incl. the drafting workspace),
    each legal tool's search + result-chat, judge-intel Q&A, and case pages all
    persist here as JSON snapshots the client can rehydrate exactly.
    """

    __tablename__ = "workspace_sessions"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Matter this session belongs to. None == owner's personal scope; a shared
    # matter makes it visible to that matter's members. See app/services/matters.py.
    matter_id = Column(String(36), nullable=True, index=True)
    # e.g. "contracts" | "tool:precedents" | "tool:oral-arguments" | "judge" | "case"
    surface = Column(String(50), nullable=False)
    title = Column(String(300), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_workspace_session_user_updated", "user_id", "updated_at"),)


class BrandingConfigDB(Base):
    """Per-installation branding configuration."""

    __tablename__ = "branding_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    firm_name = Column(String(255), default="CaseCite")
    logo_url = Column(String(500), nullable=True)
    primary_color = Column(String(20), default="#E5E5E5")
    secondary_color = Column(String(20), default="#0A0A0A")
    accent_color = Column(String(20), default="#737373")
    favicon_url = Column(String(500), nullable=True)
    custom_css = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class InstanceSecretDB(Base):
    """Instance-wide secrets editable from the admin UI (e.g. the CourtListener
    API token), stored AES-256-GCM encrypted. One row per secret name. These are
    server/instance level (not per-user) and override the .env fallback."""

    __tablename__ = "instance_secrets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    value_encrypted = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
