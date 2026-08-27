"""
Error Handlers

Registers all exception handlers on the FastAPI application:
validation errors, HTTP exceptions, value errors, permission errors,
and a general catch-all handler.
"""

import logging
import uuid as uuid_module

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.services.audit import AuditEventType, audit_service

logger = logging.getLogger(__name__)


def _generate_error_reference() -> str:
    """Generate a unique error reference ID for tracking."""
    return f"ERR-{uuid_module.uuid4().hex[:8].upper()}"


def register_error_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI application."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle request validation errors with safe messages."""
        error_ref = _generate_error_reference()

        # Build a user-friendly message from field errors. Log only the field
        # location and error type — never str(exc) or err["input"], which carry
        # the submitted body (passwords, BYOK API keys) into the log stream.
        field_errors = []
        log_fields = []
        for err in exc.errors():
            field_path = ".".join(str(loc) for loc in err.get("loc", []) if loc != "body")
            msg = err.get("msg", "Invalid value")
            if field_path:
                field_errors.append(f"{field_path}: {msg}")
            log_fields.append(f"{field_path or '<body>'}={err.get('type', 'invalid')}")
        logger.warning(
            f"Validation error [{error_ref}] at {request.url.path}: {', '.join(log_fields)}"
        )

        if field_errors:
            detail = f"Please fix the following: {'; '.join(field_errors)}"
        else:
            detail = "Request validation failed. Please check your input."

        return JSONResponse(
            status_code=422,
            content={
                "detail": detail,
                "error_ref": error_ref,
                "errors": [
                    {
                        "field": ".".join(str(loc) for loc in err.get("loc", [])),
                        "message": err.get("msg", "Invalid value"),
                    }
                    for err in exc.errors()
                ]
                if settings.debug
                else None,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions with logging."""
        error_ref = _generate_error_reference()

        # Log security-relevant errors
        if exc.status_code in [401, 403]:
            await audit_service.log_event(
                event_type=AuditEventType.ACCESS_DENIED,
                ip_address=request.client.host if request.client else None,
                details={
                    "error_ref": error_ref,
                    "path": str(request.url.path),
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                },
                success=False,
            )

        # For 500 errors in production, never expose raw detail
        detail = exc.detail
        if exc.status_code >= 500 and not settings.debug:
            logger.error(
                f"HTTP {exc.status_code} [{error_ref}]: {exc.detail} at {request.url.path}"
            )
            detail = "An internal error occurred. Please try again."

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": detail,
                "error_ref": error_ref if exc.status_code >= 500 else None,
            },
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Handle ValueError (usually validation errors)."""
        error_ref = _generate_error_reference()

        # Log the error details server-side
        logger.warning(f"ValueError [{error_ref}]: {exc} at {request.url.path}")

        # Return safe message to client
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Invalid input provided",
                "error_ref": error_ref,
            },
        )

    @app.exception_handler(PermissionError)
    async def permission_error_handler(request: Request, exc: PermissionError):
        """Handle PermissionError."""
        error_ref = _generate_error_reference()

        await audit_service.log_event(
            event_type=AuditEventType.ACCESS_DENIED,
            ip_address=request.client.host if request.client else None,
            details={
                "error_ref": error_ref,
                "path": str(request.url.path),
                "error": str(exc),
            },
            success=False,
        )

        return JSONResponse(
            status_code=403,
            content={
                "detail": "Permission denied",
                "error_ref": error_ref,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions with error reference tracking."""
        error_ref = _generate_error_reference()

        # Log full error details server-side
        logger.error(
            f"Unhandled exception [{error_ref}]: {type(exc).__name__}: {exc}", exc_info=True
        )

        await audit_service.log_event(
            event_type=AuditEventType.SUSPICIOUS_ACTIVITY,
            ip_address=request.client.host if request.client else None,
            details={
                "error_ref": error_ref,
                "path": str(request.url.path),
                "error_type": type(exc).__name__,
                # Only include error message in logs, not in response
                "error": str(exc),
            },
            success=False,
            error=str(exc),
        )

        # Return safe message to client with error reference
        if settings.debug:
            # In debug mode, include full error for development
            return JSONResponse(
                status_code=500,
                content={
                    "detail": str(exc),
                    "error_type": type(exc).__name__,
                    "error_ref": error_ref,
                },
            )
        else:
            # In production, only return error reference
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "An internal error occurred. Please contact support if this persists.",
                    "error_ref": error_ref,
                },
            )
