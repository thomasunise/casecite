"""Global politeness gate for every CourtListener request.

CourtListener's throttle objects to BURSTS, not volume — a judge-intel build
legitimately needs 100+ calls and Trends ~27, and that stays. What changes is
the delivery: every request in the whole app flows through one shared gate
that spaces request starts a minimum interval apart, caps how many are in
flight at once, and on a 429 waits out the server's Retry-After and retries
silently instead of surfacing the error. Data volume is untouched; only the
firing pattern changes.

Usage: replace ``httpx.AsyncClient(timeout=X)`` with ``cl_client(timeout=X)``
at CourtListener call sites. Everything else (headers, .get calls, context
managers) stays exactly as written.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

logger = logging.getLogger(__name__)

# ~4 requests/second steady state — a 120-call judge build completes in ~30s
# (inside its advertised 30-60s) without ever bursting.
_MIN_INTERVAL = 0.25
_MAX_CONCURRENCY = 3
_MAX_RETRIES = 3
_DEFAULT_BACKOFF = 2.0
_MAX_BACKOFF = 60.0


class _Gate:
    """Shared pacing state. Single event loop — no thread safety needed."""

    def __init__(self) -> None:
        self.semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
        self._lock = asyncio.Lock()
        self._next_start = 0.0
        self._penalty_until = 0.0

    async def wait_for_slot(self) -> None:
        """Reserve the next start time (min-interval spacing, penalty-aware)."""
        async with self._lock:
            now = time.monotonic()
            start = max(now, self._next_start, self._penalty_until)
            self._next_start = start + _MIN_INTERVAL
        delay = start - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)

    def penalize(self, seconds: float) -> None:
        """A 429 pushes the WHOLE pipe back, so every queued call waits it out."""
        until = time.monotonic() + seconds
        if until > self._penalty_until:
            self._penalty_until = until


_gate = _Gate()


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after), _MAX_BACKOFF)
        except ValueError:
            pass  # HTTP-date form — fall through to backoff
    return min(_DEFAULT_BACKOFF * (2**attempt), _MAX_BACKOFF)


class _ThrottledTransport(httpx.AsyncHTTPTransport):
    """Transport that routes every request through the shared gate."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response: httpx.Response | None = None
        for attempt in range(_MAX_RETRIES + 1):
            async with _gate.semaphore:
                await _gate.wait_for_slot()
                response = await super().handle_async_request(request)
            if response.status_code != 429 or attempt >= _MAX_RETRIES:
                return response
            delay = _retry_delay(response, attempt)
            await response.aclose()
            _gate.penalize(delay)
            logger.warning(
                "CourtListener throttled (429) — pausing %.1fs, retry %d/%d: %s",
                delay,
                attempt + 1,
                _MAX_RETRIES,
                request.url.path,
            )
            await asyncio.sleep(delay)
        return response  # type: ignore[return-value]  # loop always assigns


def cl_client(timeout: float = 60.0, **kwargs) -> httpx.AsyncClient:
    """Drop-in httpx.AsyncClient whose requests are globally paced.

    Each client gets its own transport instance (httpx closes transports with
    the client), but all transports share the module-level gate — the pacing
    is app-wide no matter how many clients are open.
    """
    return httpx.AsyncClient(timeout=timeout, transport=_ThrottledTransport(), **kwargs)
