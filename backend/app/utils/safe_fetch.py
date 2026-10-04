"""
SSRF-safe outbound HTTP fetch helpers.

Any code path that fetches a URL whose host is influenced by user input (file
pickers' download links, admin-configured endpoints, connector-supplied URLs)
must go through :func:`safe_download` rather than calling httpx directly. It:

- restricts the scheme to http/https,
- resolves the hostname and rejects private, loopback, link-local, reserved and
  cloud-metadata addresses (blocking access to 169.254.169.254, 127.0.0.1,
  10.0.0.0/8, internal services, etc.),
- requires the host to match a caller-supplied allowlist of provider domains,
- re-validates the target on every redirect hop (a naive host check is defeated
  by an allowed host that 302-redirects to an internal address),
- streams the body with a hard byte ceiling to prevent memory-exhaustion DoS.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)


class UnsafeURLError(ValueError):
    """Raised when a URL is rejected as unsafe to fetch server-side."""


_ALLOWED_SCHEMES = {"http", "https"}


def _host_matches_allowlist(host: str, allowed_hosts: tuple[str, ...]) -> bool:
    host = host.lower().rstrip(".")
    for allowed in allowed_hosts:
        allowed = allowed.lower().lstrip(".")
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def _address_is_public(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    # Reject anything that isn't a normal, globally-routable address.
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _resolve_host(host: str) -> list[str]:
    """Resolve a hostname to its IP addresses (non-blocking)."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None)
    except OSError as e:
        raise UnsafeURLError(f"Could not resolve host: {host}") from e
    return [info[4][0] for info in infos]


async def assert_public_url(url: str, allowed_hosts: tuple[str, ...]) -> None:
    """Validate that *url* is safe to fetch server-side, or raise UnsafeURLError.

    *allowed_hosts* is REQUIRED: the host must match one of the entries
    (suffix match, e.g. ``"dropbox.com"`` matches ``dl.dropboxusercontent.com``
    only if that suffix is listed; list the exact download domains). There is
    deliberately no default that skips allowlisting — every caller must state
    which provider hosts it trusts. An empty tuple rejects every host.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"Unsupported URL scheme: {parts.scheme!r}")
    host = parts.hostname
    if not host:
        raise UnsafeURLError("URL has no host")

    if not _host_matches_allowlist(host, allowed_hosts):
        raise UnsafeURLError(f"Host not allowed: {host}")

    # If the host is a literal IP, validate it directly; otherwise resolve.
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        addresses = await _resolve_host(host)

    if not addresses:
        raise UnsafeURLError(f"Host did not resolve: {host}")
    for addr in addresses:
        if not _address_is_public(addr):
            raise UnsafeURLError(f"Host resolves to a non-public address: {host} -> {addr}")


# Request headers that carry credentials; never replayed to a different origin.
_CREDENTIAL_HEADERS = {"authorization", "proxy-authorization", "cookie"}

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(url: str) -> tuple[str, str, int | None]:
    """(scheme, host, port) of *url*, with the default port made explicit."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    return scheme, (parts.hostname or "").lower(), port or _DEFAULT_PORTS.get(scheme)


async def safe_download(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_bytes: int,
    allowed_hosts: tuple[str, ...],
    timeout: float = 60.0,
    max_redirects: int = 5,
) -> bytes:
    """Fetch *url* safely and return its body, enforcing SSRF and size limits.

    *allowed_hosts* is REQUIRED — see :func:`assert_public_url`. Redirects are
    followed manually so each hop is re-validated. Raises
    :class:`UnsafeURLError` if any target is unsafe, and ``ValueError`` if the
    body exceeds *max_bytes*.

    DNS-rebinding residual: the hostname is resolved once here for validation
    and again by httpx when it actually connects. A TTL-0 DNS name whose
    records flip between the two lookups could pass validation yet connect to
    a different (internal) address. The required host allowlist is the primary
    control — only trusted provider domains should ever be listed — so
    exploiting the race additionally requires control of a listed provider's
    DNS. Pinning the resolved IP for the actual connection would close the
    race entirely and is the known residual here.

    Credentials stay with the origin they were issued for: once a redirect
    leaves the original scheme/host/port, credential headers (``Authorization``
    and friends) are dropped for that hop and every later one. Provider content
    endpoints redirect to pre-signed CDN URLs that need no token, so a bearer
    token is never handed to a second host.
    """
    current = url
    hop_headers = dict(headers) if headers else None
    origin = _origin(url)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            await assert_public_url(current, allowed_hosts)
            async with client.stream("GET", current, headers=hop_headers) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        response.raise_for_status()
                        raise UnsafeURLError("Redirect without a Location header")
                    current = str(response.url.join(location))
                    if hop_headers and _origin(current) != origin:
                        hop_headers = {
                            k: v
                            for k, v in hop_headers.items()
                            if k.lower() not in _CREDENTIAL_HEADERS
                        }
                    continue
                response.raise_for_status()
                # Enforce declared size early when available.
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise ValueError(f"Remote file exceeds the {max_bytes}-byte limit")
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > max_bytes:
                        raise ValueError(f"Remote file exceeds the {max_bytes}-byte limit")
                return bytes(chunks)
    raise UnsafeURLError(f"Too many redirects while fetching {url}")
