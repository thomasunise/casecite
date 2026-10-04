"""
Error Handlers

Registers all exception handlers on the FastAPI application:
validation errors, HTTP exceptions, value errors, permission errors,
and a general catch-all handler.

Exception MESSAGES are never copied into the audit trail and, outside DEBUG,
never into the application log: they can carry SQL parameters, document or
chat text, and secrets. Production records the exception type, the stack
frames (code locations only) and an error reference that ties the client's
response to the log line.
"""

import logging
import time
import traceback
import uuid as uuid_module

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.services.audit import AuditEventType, audit_service
from app.utils.ip_resolution import get_client_ip

logger = logging.getLogger(__name__)

# Anonymous 401s (no credentials presented at all) are what every scanner,
# expired tab and health probe produces. Auditing each one lets anyone flood
# the tamper-evident trail, so they are recorded at most once per client IP
# per window. Requests that DO present credentials are always audited.
_ANON_401_AUDIT_WINDOW_SECONDS = 60
_ANON_401_MAX_TRACKED_IPS = 10_000
_anon_401_last_audit: dict[str, float] = {}


def _generate_error_reference() -> str:
    """Generate a unique error reference ID for tracking."""
    return f"ERR-{uuid_module.uuid4().hex[:8].upper()}"


def _presented_credentials(request: Request) -> bool:
    return bool(request.headers.get("authorization") or request.cookies.get("access_token"))


def _should_audit_denial(request: Request, status_code: int, client_ip: str | None) -> bool:
    """Whether a 401/403 gets an audit entry (anonymous 401s are rate-bounded)."""
    if status_code != 401 or _presented_credentials(request):
        return True
    now = time.monotonic()
    key = client_ip or "unknown"
    last = _anon_401_last_audit.get(key)
    if last is not None and now - last < _ANON_401_AUDIT_WINDOW_SECONDS:
        return False
    if len(_anon_401_last_audit) >= _ANON_401_MAX_TRACKED_IPS:
        cutoff = now - _ANON_401_AUDIT_WINDOW_SECONDS
        for ip in [ip for ip, ts in _anon_401_last_audit.items() if ts < cutoff]:
            del _anon_401_last_audit[ip]
        if len(_anon_401_last_audit) >= _ANON_401_MAX_TRACKED_IPS:
            _anon_401_last_audit.clear()
    _anon_401_last_audit[key] = now
    return True


def _stack_locations(exc: BaseException) -> str:
    """The exception's stack frames WITHOUT its message (code locations only)."""
    return "".join(traceback.format_tb(exc.__traceback__))


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
            client_ip = get_client_ip(request)
            if _should_audit_denial(request, exc.status_code, client_ip):
                await audit_service.log_event(
                    event_type=AuditEventType.ACCESS_DENIED,
                    ip_address=client_ip,
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

        content = {
            "detail": detail,
            "error_ref": error_ref if exc.status_code >= 500 else None,
        }
        # Machine-readable reason for 403s that mean "finish a step first"
        # (app.services.auth.AuthActionRequired): password_change_required,
        # mfa_enrollment_required.
        code = getattr(exc, "code", None)
        if code:
            content["code"] = code

        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Handle ValueError (usually validation errors)."""
        error_ref = _generate_error_reference()

        # Log the error server-side. The message is only included in DEBUG: a
        # ValueError raised deep in a service can quote the offending input.
        if settings.debug:
            logger.warning(f"ValueError [{error_ref}]: {exc} at {request.url.path}")
        else:
            logger.warning(
                f"ValueError [{error_ref}] at {request.url.path}\n{_stack_locations(exc)}"
            )

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
            ip_address=get_client_ip(request),
            details={
                "error_ref": error_ref,
                "path": str(request.url.path),
                "error_type": type(exc).__name__,
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

        if settings.debug:
            # Development: full message and traceback.
            logger.error(
                f"Unhandled exception [{error_ref}]: {type(exc).__name__}: {exc}", exc_info=True
            )
        else:
            # Production: type, reference and code locations — not the message.
            logger.error(
                f"Unhandled exception [{error_ref}]: {type(exc).__name__} at "
                f"{request.url.path}\n{_stack_locations(exc)}"
            )

        await audit_service.log_event(
            event_type=AuditEventType.SUSPICIOUS_ACTIVITY,
            ip_address=get_client_ip(request),
            details={
                "error_ref": error_ref,
                "path": str(request.url.path),
                "error_type": type(exc).__name__,
            },
            success=False,
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
