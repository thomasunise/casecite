"""User & authentication models."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Index, Integer, String, false

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
    # Set on admin invite (the admin has seen the temporary password); cleared
    # by a successful password change/reset. While set, only the password-change
    # endpoints are reachable (see services.auth.get_current_user).
    must_change_password = Column(Boolean, nullable=False, default=False, server_default=false())
    # Embedded in every access/refresh token as the ``tv`` claim. Bumping it
    # (logout-all, admin force sign-out, refresh-token reuse) invalidates every
    # outstanding token for the user on every device, durably.
    token_version = Column(Integer, nullable=False, default=0, server_default="0")

    # Metadata
    company = Column(String(255), nullable=True)
    last_login = Column(DateTime, nullable=True)
    password_changed_at = Column(
        DateTime, nullable=True
    )  # Tracks last password change for expiry policy
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_user_email_active", "email", "is_active"),)
