"""
Unit tests for the Resilience service.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import AsyncMock

import pytest
from app.services.resilience import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
    _circuit_breakers,
    get_circuit_breaker,
    retry_with_backoff,
)


@pytest.fixture(autouse=True)
def clear_circuit_breakers():
    """Clear circuit breaker registry before each test."""
    _circuit_breakers.clear()
    yield
    _circuit_breakers.clear()


# =============================================================================
# CircuitBreaker Tests
# =============================================================================


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=60)

        for i in range(3):
            cb.record_failure(Exception(f"Error {i}"))

        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=5, recovery_timeout=60)

        cb.record_failure(Exception("Error 1"))
        cb.record_failure(Exception("Error 2"))

        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_success_resets_from_half_open(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60)

        cb.record_failure(Exception("Error"))
        assert cb.state == CircuitState.OPEN

        # Manually set state to HALF_OPEN to simulate recovery timeout elapsed
        cb.state = CircuitState.HALF_OPEN

        assert cb.can_execute() is True
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_failure_in_half_open_reopens(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60)

        cb.record_failure(Exception("Error"))
        assert cb.state == CircuitState.OPEN

        # Manually transition to half_open
        cb.state = CircuitState.HALF_OPEN
        assert cb.can_execute() is True

        # Fail again
        cb.record_failure(Exception("Still failing"))
        assert cb.state == CircuitState.OPEN

    def test_get_status(self):
        cb = CircuitBreaker("test-service", failure_threshold=5, recovery_timeout=30)
        cb.record_success()
        cb.record_success()

        status = cb.get_status()
        assert status["name"] == "test-service"
        assert status["state"] == "closed"
        assert status["success_count"] == 2
        assert status["failure_count"] == 0

    def test_records_last_failure_time(self):
        cb = CircuitBreaker("test", failure_threshold=5, recovery_timeout=30)
        cb.record_failure(Exception("fail"))

        assert cb.last_failure_time is not None


# =============================================================================
# get_circuit_breaker Tests
# =============================================================================


class TestCircuitBreakerRegistry:
    """Tests for circuit breaker registry functions."""

    def test_get_creates_new_breaker(self):
        cb = get_circuit_breaker("openai")
        assert isinstance(cb, CircuitBreaker)
        assert cb.name == "openai"

    def test_get_returns_same_instance(self):
        cb1 = get_circuit_breaker("openai")
        cb2 = get_circuit_breaker("openai")
        assert cb1 is cb2


# =============================================================================
# retry_with_backoff Tests
# =============================================================================


class TestRetryWithBackoff:
    """Tests for retry_with_backoff."""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        func = AsyncMock(return_value="success")

        result = await retry_with_backoff(func, max_attempts=3, base_delay=0.01)
        assert result == "success"
        assert func.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self):
        func = AsyncMock(side_effect=[ValueError("fail"), ValueError("fail"), "ok"])

        result = await retry_with_backoff(
            func, max_attempts=3, base_delay=0.01, retryable_exceptions=(ValueError,)
        )
        assert result == "ok"
        assert func.call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_fail(self):
        func = AsyncMock(side_effect=ValueError("always fail"))

        with pytest.raises(ValueError, match="always fail"):
            await retry_with_backoff(
                func,
                max_attempts=2,
                base_delay=0.01,
                retryable_exceptions=(ValueError,),
            )
        assert func.call_count == 2

    @pytest.mark.asyncio
    async def test_uses_fallback_after_failure(self):
        func = AsyncMock(side_effect=ValueError("fail"))
        fallback = AsyncMock(return_value="fallback_value")

        result = await retry_with_backoff(
            func,
            max_attempts=1,
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
            fallback=fallback,
        )
        assert result == "fallback_value"

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_uses_fallback(self):
        cb = get_circuit_breaker("test-cb", failure_threshold=1, recovery_timeout=9999)
        cb.record_failure(Exception("fail"))

        func = AsyncMock(return_value="should not reach")
        fallback = AsyncMock(return_value="fallback")

        result = await retry_with_backoff(
            func,
            max_attempts=3,
            circuit_breaker_name="test-cb",
            fallback=fallback,
        )
        assert result == "fallback"
        func.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_raises_without_fallback(self):
        cb = get_circuit_breaker("test-raise", failure_threshold=1, recovery_timeout=9999)
        cb.record_failure(Exception("fail"))

        func = AsyncMock()

        with pytest.raises(CircuitBreakerOpen):
            await retry_with_backoff(func, max_attempts=3, circuit_breaker_name="test-raise")


class TestNonRetryableErrors:
    """Request-level errors (rejected key, bad config) are the caller's fault,
    not the upstream service's."""

    @pytest.mark.asyncio
    async def test_non_retryable_error_is_raised_once_and_not_counted(self):
        func = AsyncMock(side_effect=PermissionError("key rejected"))
        func.__name__ = "embed"

        with pytest.raises(PermissionError):
            await retry_with_backoff(
                func,
                max_attempts=3,
                base_delay=0.001,
                circuit_breaker_name="embeddings:user-a",
                is_retryable=lambda e: not isinstance(e, PermissionError),
            )

        assert func.await_count == 1
        breaker = get_circuit_breaker("embeddings:user-a")
        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_retryable_errors_still_retry_and_count(self):
        func = AsyncMock(side_effect=ConnectionError("reset"))
        func.__name__ = "embed"

        with pytest.raises(ConnectionError):
            await retry_with_backoff(
                func,
                max_attempts=3,
                base_delay=0.001,
                circuit_breaker_name="embeddings:user-a",
                is_retryable=lambda e: not isinstance(e, PermissionError),
            )

        assert func.await_count == 3
        assert get_circuit_breaker("embeddings:user-a").failure_count == 3


class TestBreakerRegistryBound:
    def test_registry_does_not_grow_without_limit(self):
        from app.services import resilience

        for i in range(resilience._MAX_CIRCUIT_BREAKERS + 25):
            get_circuit_breaker(f"embeddings:key-{i}")

        assert len(_circuit_breakers) == resilience._MAX_CIRCUIT_BREAKERS
        assert "embeddings:key-0" not in _circuit_breakers  # oldest healthy one evicted

    def test_a_tripped_breaker_outlives_healthy_ones(self):
        from app.services import resilience

        tripped = get_circuit_breaker("embeddings:bad-key")
        tripped.state = CircuitState.OPEN
        for i in range(resilience._MAX_CIRCUIT_BREAKERS + 5):
            get_circuit_breaker(f"embeddings:key-{i}")

        assert _circuit_breakers["embeddings:bad-key"] is tripped
