"""
Secure IP Resolution Utility

Provides CIDR-aware trusted proxy parsing and secure right-to-left
X-Forwarded-For walking to prevent IP spoofing attacks.

Used by: security middleware and auth endpoints.
"""

import ipaddress
import logging
import os
from functools import lru_cache

from fastapi import Request

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _parse_trusted_proxies() -> tuple[
    tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
    tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...],
]:
    """Parse TRUSTED_PROXIES env var into networks and addresses.

    Supports both individual IPs and CIDR notation (e.g. "10.0.0.0/8,172.16.0.0/12,192.168.1.1").
    Results are cached after first call.
    """
    raw = os.environ.get("TRUSTED_PROXIES", "")
    entries = [e.strip() for e in raw.split(",") if e.strip()]

    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []

    for entry in entries:
        try:
            if "/" in entry:
                networks.append(ipaddress.ip_network(entry, strict=False))
            else:
                addresses.append(ipaddress.ip_address(entry))
        except ValueError:
            logger.warning("Invalid TRUSTED_PROXIES entry: %s", entry)

    return tuple(networks), tuple(addresses)


def _validate_ip(ip_str: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Validate and normalize an IP address string. Returns None if invalid."""
    try:
        return ipaddress.ip_address(ip_str.strip())
    except (ValueError, AttributeError):
        return None


def _is_trusted(ip_str: str) -> bool:
    """Check whether an IP is in the trusted proxy list (supports CIDR)."""
    addr = _validate_ip(ip_str)
    if addr is None:
        return False

    networks, addresses = _parse_trusted_proxies()

    if addr in addresses:
        return True

    for network in networks:
        if addr in network:
            return True

    return False


def get_client_ip(request: Request) -> str:
    """Get the real client IP from a request, handling reverse proxies securely.

    Algorithm:
    1. Get the direct connection IP.
    2. If the direct IP is not trusted, return it immediately (no proxy headers honored).
    3. Walk X-Forwarded-For right-to-left, returning the first untrusted valid IP.
    4. Fall back to X-Real-IP if present and valid.
    5. Fall back to direct IP.
    """
    direct_ip = request.client.host if request.client else "unknown"

    # If no trusted proxies configured or direct IP isn't trusted, return direct IP
    if not _is_trusted(direct_ip):
        return direct_ip

    # Walk X-Forwarded-For right-to-left
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ips = [ip.strip() for ip in forwarded.split(",")]
        for ip_str in reversed(ips):
            if _validate_ip(ip_str) is None:
                continue  # skip malformed entries
            if not _is_trusted(ip_str):
                return ip_str
        # All IPs in the chain are trusted — return leftmost
        if ips and _validate_ip(ips[0]):
            return ips[0].strip()

    # Fall back to X-Real-IP
    real_ip = request.headers.get("x-real-ip")
    if real_ip and _validate_ip(real_ip):
        return real_ip.strip()

    return direct_ip
