"""
Tests for domain-separated key derivation and CSRF signing.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from app.middleware.csrf import generate_signed_csrf_token, verify_csrf_token
from app.utils.keys import derive_subkey


class TestDeriveSubkey:
    def test_deterministic(self):
        assert derive_subkey("jwt-hs256") == derive_subkey("jwt-hs256")

    def test_different_purposes_differ(self):
        assert derive_subkey("jwt-hs256") != derive_subkey("csrf")
        assert derive_subkey("csrf") != derive_subkey("data")

    def test_length(self):
        assert len(derive_subkey("jwt-hs256")) == 32
        assert len(derive_subkey("csrf", length=16)) == 16

    def test_not_equal_to_raw_secret(self):
        # The derived key must not be the raw secret (that would defeat separation).
        assert derive_subkey("jwt-hs256") != b"test-secret-key-for-testing-only-32chars!"


class TestCsrfRoundtrip:
    def test_valid_token_verifies(self):
        token = generate_signed_csrf_token()
        assert verify_csrf_token(token) is True

    def test_tampered_token_rejected(self):
        token = generate_signed_csrf_token()
        body, _sig = token.rsplit(".", 1)
        assert verify_csrf_token(body + ".deadbeef") is False

    def test_garbage_rejected(self):
        assert verify_csrf_token("not-a-token") is False
        assert verify_csrf_token("") is False
