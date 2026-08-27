"""
Structured logging configuration.

Emits one JSON object per log line with a correlation id, so log lines can be
tied back to a request (X-Request-ID) across the app. Previously there was no
logging configuration at all — format/level depended on uvicorn defaults and the
generated request id never reached log lines (SOC 2 CC7.2 monitoring).

Call :func:`configure_logging` once at startup, before the app handles requests.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar

# Set per-request by RequestIdMiddleware; empty outside a request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("")
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", "")
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Install a root handler with the request-id filter.

    ``json_format=False`` falls back to a plain text format that still includes
    the request id — useful for local development.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    if json_format:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Align uvicorn's loggers with our handler so their lines are structured too.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
