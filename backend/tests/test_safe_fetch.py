"""
Tests for the SSRF-safe outbound fetch helper.

These guard the picker/connector SSRF fix: server-side fetches must reject
private/loopback/link-local/metadata targets and enforce a host allowlist.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import AsyncMock, patch

import pytest
from app.utils.safe_fetch import UnsafeURLError, assert_public_url


class TestSchemeValidation:
    async def test_rejects_file_scheme(self):
        with pytest.raises(UnsafeURLError):
            await assert_public_url("file:///etc/passwd", allowed_hosts=("example.com",))

    async def test_rejects_gopher_scheme(self):
        with pytest.raises(UnsafeURLError):
            await assert_public_url("gopher://127.0.0.1:6379/_INFO", allowed_hosts=("127.0.0.1",))

    async def test_rejects_no_host(self):
        with pytest.raises(UnsafeURLError):
            await assert_public_url("https://", allowed_hosts=("example.com",))


class TestPrivateAddressBlocking:
    async def test_rejects_cloud_metadata_ip_literal(self):
        with pytest.raises(UnsafeURLError):
            await assert_public_url(
                "http://169.254.169.254/latest/meta-data/",
                allowed_hosts=("169.254.169.254",),
            )

    async def test_rejects_loopback_literal(self):
        with pytest.raises(UnsafeURLError):
            await assert_public_url("http://127.0.0.1:6379/", allowed_hosts=("127.0.0.1",))

    async def test_rejects_private_10_literal(self):
        with pytest.raises(UnsafeURLError):
            await assert_public_url("http://10.1.2.3/internal", allowed_hosts=("10.1.2.3",))

    async def test_rejects_private_192_168_literal(self):
        with pytest.raises(UnsafeURLError):
            await assert_public_url("http://192.168.0.1/", allowed_hosts=("192.168.0.1",))

    async def test_rejects_hostname_resolving_to_private(self):
        # A public-looking hostname that resolves to an internal IP.
        with (
            patch(
                "app.utils.safe_fetch._resolve_host",
                new=AsyncMock(return_value=["10.0.0.5"]),
            ),
            pytest.raises(UnsafeURLError),
        ):
            await assert_public_url("https://evil.example.com/x", allowed_hosts=("example.com",))

    async def test_allows_hostname_resolving_to_public(self):
        with patch(
            "app.utils.safe_fetch._resolve_host",
            new=AsyncMock(return_value=["93.184.216.34"]),
        ):
            # Should not raise.
            await assert_public_url("https://example.com/x", allowed_hosts=("example.com",))


class TestHostAllowlist:
    async def test_rejects_host_not_in_allowlist(self):
        with (
            patch(
                "app.utils.safe_fetch._resolve_host",
                new=AsyncMock(return_value=["93.184.216.34"]),
            ),
            pytest.raises(UnsafeURLError),
        ):
            await assert_public_url("https://attacker.com/x", allowed_hosts=("dropbox.com",))

    async def test_allows_subdomain_of_allowlisted_host(self):
        with patch(
            "app.utils.safe_fetch._resolve_host",
            new=AsyncMock(return_value=["93.184.216.34"]),
        ):
            await assert_public_url(
                "https://dl.dropboxusercontent.com/f", allowed_hosts=("dropboxusercontent.com",)
            )

    async def test_allowlist_does_not_match_suffix_trick(self):
        # notdropbox.com must NOT match an allowlist of dropbox.com
        with (
            patch(
                "app.utils.safe_fetch._resolve_host",
                new=AsyncMock(return_value=["93.184.216.34"]),
            ),
            pytest.raises(UnsafeURLError),
        ):
            await assert_public_url("https://notdropbox.com/x", allowed_hosts=("dropbox.com",))


class TestAllowlistRequired:
    async def test_allowed_hosts_parameter_is_required(self):
        # No default may exist that skips host allowlisting.
        with pytest.raises(TypeError):
            await assert_public_url("https://example.com/x")
