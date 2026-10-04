"""
Request ID Middleware

Ensures every request/response carries an X-Request-ID header for tracing.
Respects incoming values (e.g. from a reverse proxy) and generates a UUID4
when none is provided.
"""

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import request_id_var


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id
        # Expose to the logging filter so every log line during this request is
        # tagged with the same correlation id.
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response
