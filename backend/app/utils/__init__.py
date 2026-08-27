"""Utility modules for CaseCite backend."""

from app.utils.error_handler import (
    ERROR_MESSAGES,
    generate_error_reference,
    handle_service_error,
    log_and_raise,
    safe_error_response,
)

__all__ = [
    "safe_error_response",
    "log_and_raise",
    "handle_service_error",
    "generate_error_reference",
    "ERROR_MESSAGES",
]
