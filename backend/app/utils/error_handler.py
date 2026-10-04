"""
Centralized Error Handler - Production-Safe Error Responses

Returns safe error messages to clients without exposing internal
implementation details, stack traces, or sensitive information.

Usage:
    from app.utils.error_handler import handle_service_error

    except (ValueError, KeyError, OSError) as e:
        raise handle_service_error(e, "Failed to process document", logger)
"""

import logging

from fastapi import HTTPException


def handle_service_error(e: Exception, operation: str, logger: logging.Logger) -> HTTPException:
    """
    Log a service-layer error and return an HTTPException.

    Intended for the common router pattern of catching broad service exceptions
    and converting them to 500 responses.  Keeps the log message and user-facing
    detail consistent.

    Usage:
        except (ValueError, KeyError, OSError) as e:
            raise handle_service_error(e, "Failed to delete document", logger)
    """
    logger.error(f"{operation}: {e}", exc_info=True)
    return HTTPException(status_code=500, detail=f"{operation}. Please try again.")
