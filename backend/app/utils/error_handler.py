"""
Centralized Error Handler - Production-Safe Error Responses

This module provides utilities for returning safe error messages to clients
without exposing internal implementation details, stack traces, or sensitive
information.

Usage:
    from app.utils.error_handler import safe_error_response, log_and_raise

    # In router handlers:
    except Exception as e:
        raise log_and_raise(e, "Failed to process document", logger)
"""

import logging
import uuid

from fastapi import HTTPException


def generate_error_reference() -> str:
    """Generate a unique error reference ID for tracking."""
    return f"ERR-{uuid.uuid4().hex[:8].upper()}"


def safe_error_response(
    status_code: int,
    user_message: str,
    logger: logging.Logger | None = None,
    exception: Exception | None = None,
    context: str | None = None,
) -> HTTPException:
    """
    Create a production-safe HTTPException with proper logging.

    Args:
        status_code: HTTP status code (400, 404, 500, etc.)
        user_message: Safe message to return to the client
        logger: Logger instance for recording the error
        exception: The actual exception (logged but not exposed)
        context: Additional context for logging

    Returns:
        HTTPException with safe error message
    """
    error_ref = generate_error_reference()

    # Log the full error details server-side
    if logger and exception:
        log_message = f"[{error_ref}]"
        if context:
            log_message += f" {context}:"
        log_message += f" {type(exception).__name__}: {exception}"

        if status_code >= 500:
            logger.error(log_message, exc_info=True)
        else:
            logger.warning(log_message)

    # Return safe message to client
    detail = user_message
    if status_code >= 500:
        detail = f"{user_message} (Reference: {error_ref})"

    return HTTPException(status_code=status_code, detail=detail)


def log_and_raise(
    exception: Exception,
    user_message: str,
    logger: logging.Logger,
    status_code: int = 500,
    context: str | None = None,
) -> HTTPException:
    """
    Log an exception and raise a safe HTTPException.

    This is a convenience function for the common pattern of:
        logger.error(...)
        raise HTTPException(...)

    Args:
        exception: The exception that was caught
        user_message: Safe message to return to the client
        logger: Logger instance
        status_code: HTTP status code (default 500)
        context: Additional context for logging

    Returns:
        HTTPException to be raised

    Usage:
        except Exception as e:
            raise log_and_raise(e, "Failed to process document", logger)
    """
    return safe_error_response(
        status_code=status_code,
        user_message=user_message,
        logger=logger,
        exception=exception,
        context=context,
    )


def handle_service_error(e: Exception, operation: str, logger: logging.Logger) -> HTTPException:
    """
    Log a service-layer error and return an HTTPException.

    Intended for the common router pattern of catching broad service exceptions
    and converting them to 500 responses.  Keeps the log message and user-facing
    detail consistent.

    Usage:
        except (ValueError, KeyError, OSError) as e:
            raise handle_service_error(e, "Failed to create discovery set", logger)
    """
    logger.error(f"{operation}: {e}", exc_info=True)
    return HTTPException(status_code=500, detail=f"{operation}. Please try again.")


# Common error messages for reuse across routers
ERROR_MESSAGES = {
    # Generic
    "internal_error": "An internal error occurred. Please try again later.",
    "invalid_input": "Invalid input provided. Please check your request.",
    "not_found": "The requested resource was not found.",
    "unauthorized": "Authentication required.",
    "forbidden": "You do not have permission to perform this action.",
    # Documents
    "document_upload_failed": "Failed to upload document. Please ensure the file is valid.",
    "document_processing_failed": "Failed to process document. Please try again.",
    "document_not_found": "Document not found.",
    # Chat/RAG
    "chat_error": "Failed to process your query. Please try again.",
    "search_error": "Search operation failed. Please try again.",
    # Authentication
    "auth_failed": "Authentication failed. Please try again.",
    "token_invalid": "Invalid or expired token.",  # nosec B105 - error message, not password
    # Connectors
    "connector_auth_failed": "Failed to authenticate with external service.",
    "connector_sync_failed": "Failed to sync files. Please try again.",
    # Legal features
    "analysis_failed": "Document analysis failed. Please try again.",
    "comparison_failed": "Document comparison failed. Please check your input.",
    "template_failed": "Template operation failed. Please try again.",
    "discovery_failed": "Discovery operation failed. Please try again.",
    "pleading_failed": "Pleading operation failed. Please try again.",
    # Judge intelligence
    "judge_search_failed": "Judge search failed. Please try again.",
    "judge_profile_failed": "Failed to retrieve judge profile.",
    # Workflows
    "workflow_failed": "Workflow operation failed. Please try again.",
}
