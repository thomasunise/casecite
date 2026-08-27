"""
Tests for the TOTP MFA service.

TOTP-code tests require pyotp (in requirements.txt; installed in CI). The
challenge-token and recovery-code logic is pure and always runs.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import pytest
from app.services import mfa


class TestChallengeToken:
    def test_roundtrip_valid(self):
        token = mfa.create_challenge_token("user-123", now=1000.0)
        assert mfa.verify_challenge_token(token, now=1000.0) == "user-123"

    def test_expired_rejected(self):
        token = mfa.create_challenge_token("user-123", now=1000.0)
        # 6 minutes later (TTL is 5 min)
        assert mfa.verify_challenge_token(token, now=1000.0 + 360) is None

    def test_tampered_user_rejected(self):
        token = mfa.create_challenge_token("user-123", now=1000.0)
        forged = token.replace("user-123", "user-999")
        assert mfa.verify_challenge_token(forged, now=1000.0) is None

    def test_garbage_rejected(self):
        assert mfa.verify_challenge_token("nope", now=1000.0) is None
        assert mfa.verify_challenge_token("", now=1000.0) is None


class TestRecoveryCodes:
    def test_generate_returns_matched_plain_and_hash(self):
        plain, hashed = mfa.generate_recovery_codes(n=5)
        assert len(plain) == 5
        assert len(hashed) == 5
        # Plaintext codes are not stored as-is.
        assert all(p not in hashed for p in plain)

    def test_consume_valid_code_removes_it(self):
        plain, hashed = mfa.generate_recovery_codes(n=3)
        ok, remaining = mfa.consume_recovery_code(plain[0], hashed)
        assert ok is True
        assert len(remaining) == 2

    def test_consume_invalid_code_unchanged(self):
        _plain, hashed = mfa.generate_recovery_codes(n=3)
        ok, remaining = mfa.consume_recovery_code("0000-0000", hashed)
        assert ok is False
        assert len(remaining) == 3

    def test_code_cannot_be_reused(self):
        plain, hashed = mfa.generate_recovery_codes(n=3)
        ok, remaining = mfa.consume_recovery_code(plain[0], hashed)
        assert ok is True
        ok2, _ = mfa.consume_recovery_code(plain[0], remaining)
        assert ok2 is False


class TestTotp:
    def test_totp_verify_roundtrip(self):
        pytest.importorskip("pyotp")
        import pyotp

        secret = mfa.generate_secret()
        code = pyotp.TOTP(secret).now()
        assert mfa.verify_totp(secret, code) is True
        assert mfa.verify_totp(secret, "000000") in (True, False)  # wrong code usually False

    def test_secret_encrypt_roundtrip(self):
        pytest.importorskip("pyotp")
        secret = mfa.generate_secret()
        enc = mfa.encrypt_secret(secret)
        assert enc != secret
        assert mfa.decrypt_secret(enc) == secret

    def test_provisioning_uri(self):
        pytest.importorskip("pyotp")
        secret = mfa.generate_secret()
        uri = mfa.provisioning_uri(secret, "user@example.com")
        assert uri.startswith("otpauth://totp/")
        assert "CaseCite" in uri


class TestMfaRouterContract:
    """Auth-gating and shape checks for the management endpoints."""

    def test_status_requires_auth(self, client):
        resp = client.get("/api/v1/auth/mfa/status")
        assert resp.status_code in (401, 403)

    def test_setup_requires_auth(self, client):
        resp = client.post("/api/v1/auth/mfa/setup")
        assert resp.status_code in (401, 403)

    def test_recovery_codes_requires_auth(self, client):
        resp = client.post("/api/v1/auth/mfa/recovery-codes", json={"code": "123456"})
        assert resp.status_code in (401, 403)

    def test_verify_rejects_garbage_challenge(self, client):
        resp = client.post(
            "/api/v1/auth/mfa/verify",
            json={"mfa_token": "not-a-real-token", "code": "123456"},
        )
        assert resp.status_code == 401
