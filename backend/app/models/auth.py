"""User & authentication models."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Index, String

from app.models.base import Base


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255))  # Null for SSO users
    roles = Column(JSON, default=lambda: ["attorney"])  # List of UserRole values

    # Azure AD integration
    azure_oid = Column(String(255), unique=True, nullable=True, index=True)
    tenant_id = Column(String(255), nullable=True)

    # Security
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String(255), nullable=True)  # Encrypted TOTP secret
    mfa_recovery_codes = Column(JSON, nullable=True)  # List of hashed recovery codes
    email_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Metadata
    company = Column(String(255), nullable=True)
    last_login = Column(DateTime, nullable=True)
    password_changed_at = Column(
        DateTime, nullable=True
    )  # Tracks last password change for expiry policy
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_user_email_active", "email", "is_active"),)
