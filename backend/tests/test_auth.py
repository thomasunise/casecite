"""
Tests for authentication service.
"""

import pytest
from app.services.auth import AuthService, User, UserRole


class TestAuthService:
    """Test cases for AuthService."""

    def test_create_access_token(self):
        """Test access token creation."""
        auth = AuthService()
        user = User(
            id="test-123", email="test@example.com", name="Test User", roles=[UserRole.ATTORNEY]
        )

        token = auth.create_access_token(user)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_valid_token(self):
        """Test verification of a valid token."""
        auth = AuthService()
        user = User(
            id="test-123", email="test@example.com", name="Test User", roles=[UserRole.ATTORNEY]
        )

        token = auth.create_access_token(user)
        token_data = auth.verify_token(token)

        assert token_data.user_id == user.id
        assert token_data.email == user.email
        assert "attorney" in token_data.roles

    def test_verify_invalid_token(self):
        """Test verification of an invalid token."""
        from fastapi import HTTPException

        auth = AuthService()

        with pytest.raises(HTTPException) as exc_info:
            auth.verify_token("invalid-token")

        assert exc_info.value.status_code == 401

    def test_revoke_token(self):
        """Test token revocation."""
        from fastapi import HTTPException

        auth = AuthService()
        user = User(
            id="test-123", email="test@example.com", name="Test User", roles=[UserRole.ATTORNEY]
        )

        token = auth.create_access_token(user)
        token_data = auth.verify_token(token)

        # Revoke the token
        auth.revoke_token(token_data.jti)

        # Token should now be invalid
        with pytest.raises(HTTPException) as exc_info:
            auth.verify_token(token)

        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail.lower()

    def test_create_refresh_token(self):
        """Test refresh token creation."""
        auth = AuthService()
        user = User(
            id="test-123", email="test@example.com", name="Test User", roles=[UserRole.ATTORNEY]
        )

        token = auth.create_refresh_token(user)

        assert token is not None
        assert isinstance(token, str)

    def test_check_permission_with_valid_role(self):
        """Test permission check with valid role."""
        auth = AuthService()

        result = auth.check_permission(
            user_roles=["attorney", "admin"], required_roles=[UserRole.ATTORNEY]
        )

        assert result is True

    def test_check_permission_with_invalid_role(self):
        """Test permission check with invalid role."""
        auth = AuthService()

        result = auth.check_permission(user_roles=["viewer"], required_roles=[UserRole.ADMIN])

        assert result is False

    def test_token_expiration(self):
        """Test that tokens have correct expiration."""
        auth = AuthService()
        user = User(
            id="test-123", email="test@example.com", name="Test User", roles=[UserRole.ATTORNEY]
        )

        token = auth.create_access_token(user)
        token_data = auth.verify_token(token)

        # Token should expire after it was issued
        assert token_data.exp > token_data.iat

        # Expiration should be roughly access_token_expire after issuance
        expected_lifetime = (token_data.exp - token_data.iat).total_seconds()
        configured_lifetime = auth.access_token_expire.total_seconds()
        # Allow for some tolerance (within 60 seconds)
        assert abs(expected_lifetime - configured_lifetime) < 60


class TestUserRole:
    """Test cases for UserRole enum."""

    def test_role_values(self):
        """Test that all roles have correct values."""
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.ATTORNEY.value == "attorney"
        assert UserRole.PARALEGAL.value == "paralegal"
        assert UserRole.VIEWER.value == "viewer"
