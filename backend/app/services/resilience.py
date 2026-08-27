"""
API Resilience Module - Enterprise-Grade Error Handling

Provides:
- Exponential backoff with jitter for retries
- Circuit breaker pattern to prevent cascade failures
- Comprehensive logging
"""

import asyncio
import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypeVar

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.

    - CLOSED: Normal operation, track failures
    - OPEN: Service is failing, reject requests immediately
    - HALF_OPEN: Allow one request to test recovery
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = None,
        recovery_timeout: float = None,
        expected_exceptions: tuple = (Exception,),
    ):
        self.name = name
        self.failure_threshold = failure_threshold or settings.circuit_breaker_threshold
        self.recovery_timeout = recovery_timeout or settings.circuit_breaker_timeout
        self.expected_exceptions = expected_exceptions

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.success_count = 0

    def can_execute(self) -> bool:
        """Check if request should be allowed."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time:
                elapsed = (datetime.now(UTC) - self.last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN state")
                    return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            return True

        return False

    def record_success(self):
        """Record a successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            logger.info(f"Circuit breaker '{self.name}' CLOSED after successful recovery")
        self.success_count += 1

    def record_failure(self, error: Exception):
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now(UTC)

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker '{self.name}' OPEN after failed recovery attempt")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker '{self.name}' OPEN after {self.failure_count} failures. "
                f"Last error: {error}"
            )

    def get_status(self) -> dict[str, Any]:
        """Get circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
        }


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open."""

    pass


# Global circuit breakers registry
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, **kwargs)
    return _circuit_breakers[name]


async def retry_with_backoff(
    func: Callable[..., T],
    *args,
    max_attempts: int = None,
    base_delay: float = None,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple = (Exception,),
    circuit_breaker_name: str | None = None,
    fallback: Callable[..., T] | None = None,
    **kwargs,
) -> T:
    """
    Execute an async function with exponential backoff retry.

    Args:
        func: Async function to execute
        max_attempts: Maximum retry attempts (default from settings)
        base_delay: Initial delay between retries (default from settings)
        max_delay: Maximum delay cap
        exponential_base: Base for exponential calculation
        jitter: Add random jitter to prevent thundering herd
        retryable_exceptions: Exceptions that trigger retry
        circuit_breaker_name: Name of circuit breaker to use
        fallback: Fallback function if all retries fail

    Returns:
        Result of func or fallback

    Raises:
        Last exception if all retries fail and no fallback
    """
    max_attempts = max_attempts or settings.api_retry_attempts
    base_delay = base_delay or settings.api_retry_delay

    # Check circuit breaker
    circuit_breaker = None
    if circuit_breaker_name:
        circuit_breaker = get_circuit_breaker(circuit_breaker_name)
        if not circuit_breaker.can_execute():
            if fallback:
                logger.warning(f"Circuit breaker '{circuit_breaker_name}' is open, using fallback")
                return (
                    await fallback(*args, **kwargs)
                    if asyncio.iscoroutinefunction(fallback)
                    else fallback(*args, **kwargs)
                )
            raise CircuitBreakerOpen(f"Circuit breaker '{circuit_breaker_name}' is open")

    last_exception = None

    for attempt in range(1, max_attempts + 1):
        try:
            result = await func(*args, **kwargs)
            if circuit_breaker:
                circuit_breaker.record_success()
            return result

        except retryable_exceptions as e:
            last_exception = e

            if circuit_breaker:
                circuit_breaker.record_failure(e)

            if attempt == max_attempts:
                logger.error(f"All {max_attempts} retry attempts failed for {func.__name__}: {e}")
                break

            # Calculate delay with exponential backoff
            delay = min(base_delay * (exponential_base ** (attempt - 1)), max_delay)

            # Add jitter (±25% randomization) - not for crypto, just timing variance
            if jitter:
                delay = delay * (0.75 + random.random() * 0.5)  # nosec B311

            logger.warning(
                f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. "
                f"Retrying in {delay:.2f}s"
            )

            await asyncio.sleep(delay)

    # All retries failed
    if fallback:
        logger.warning(f"Using fallback for {func.__name__} after all retries failed")
        return (
            await fallback(*args, **kwargs)
            if asyncio.iscoroutinefunction(fallback)
            else fallback(*args, **kwargs)
        )

    raise last_exception
