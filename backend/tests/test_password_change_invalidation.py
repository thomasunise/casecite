"""
Tests for the password-change token-invalidation helper.

Guards the fix that makes a password reset invalidate all outstanding access and
refresh tokens (tokens issued before password_changed_at are rejected).
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from datetime import UTC, datetime

from app.services.auth import _token_predates_password_change


class TestTokenPredatesPasswordChange:
    def test_token_issued_before_change_is_invalid(self):
        pwc = datetime(2026, 7, 1, 12, 0, 0)  # naive UTC, as stored in DB
        token_iat = datetime(2026, 7, 1, 11, 0, 0, tzinfo=UTC)  # 1h earlier
        assert _token_predates_password_change(token_iat, pwc) is True

    def test_token_issued_after_change_is_valid(self):
        pwc = datetime(2026, 7, 1, 12, 0, 0)
        token_iat = datetime(2026, 7, 1, 13, 0, 0, tzinfo=UTC)  # 1h later
        assert _token_predates_password_change(token_iat, pwc) is False

    def test_token_at_same_time_within_skew_is_valid(self):
        """A token minted at ~reset time must not be spuriously rejected."""
        pwc = datetime(2026, 7, 1, 12, 0, 0)
        token_iat = datetime(2026, 7, 1, 11, 59, 58, tzinfo=UTC)  # 2s before, within 5s skew
        assert _token_predates_password_change(token_iat, pwc) is False

    def test_token_well_before_change_beyond_skew_is_invalid(self):
        pwc = datetime(2026, 7, 1, 12, 0, 0)
        token_iat = datetime(2026, 7, 1, 11, 59, 50, tzinfo=UTC)  # 10s before, beyond skew
        assert _token_predates_password_change(token_iat, pwc) is True

    def test_handles_naive_token_iat(self):
        pwc = datetime(2026, 7, 1, 12, 0, 0)
        token_iat = datetime(2026, 7, 1, 10, 0, 0)  # naive
        assert _token_predates_password_change(token_iat, pwc) is True

    def test_handles_aware_password_changed_at(self):
        pwc = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)  # aware variant
        token_iat = datetime(2026, 7, 1, 10, 0, 0, tzinfo=UTC)
        assert _token_predates_password_change(token_iat, pwc) is True
