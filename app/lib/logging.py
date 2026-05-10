"""
Structured logging configuration.

Provides a ``StructuredFormatter`` and a ``configure_logging()`` function
that wire up all application loggers (audit, middleware, router) to use a
single, consistent log format on stdout:

    [2026-05-10T12:22:56.556Z] [MainThread] [audit.py:39] [INFO] [requestId=abc]: message

Uvicorn's default access logger is disabled because the middleware already
records richer request/response metadata in the same format.
"""

import logging
import sys
from datetime import datetime, timezone

from app.lib.context import request_id_var


class StructuredFormatter(logging.Formatter):
    """
    Unified log formatter that outputs every record in the format::

        [timestamp] [thread] [file:line] [level] [requestId=...]: message

    The envelope carries timestamp, thread, source location, level, and the
    request-scoped ``requestId`` (read from a ContextVar or the LogRecord's
    ``extra``).  The message body is typically a JSON string with event-specific
    fields produced by the audit or middleware layers.

    This gives a single, consistent format for every log line, whether it
    originates from the middleware, the audit layer, or any other logger.
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        # Prefer request_id attached via extra={}; fall back to ContextVar
        rid = getattr(record, "request_id", "") or request_id_var.get("")
        msg = record.getMessage()
        return (
            f"[{ts}] [{record.threadName}] [{record.filename}:{record.lineno}] "
            f"[{record.levelname}] [requestId={rid}]: {msg}"
        )


def configure_logging() -> None:
    """
    Set up structured logging for the entire application.

    All application loggers (``app.audit``, ``app.middleware``, ``app.router``)
    share the same ``StructuredFormatter`` so every log line uses the same
    envelope format.

    Uvicorn's default access logger (``uvicorn.access``) is suppressed because
    the middleware already records richer request/response metadata in the same
    format.
    """
    formatter = StructuredFormatter()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    for name in ("app.audit", "app.middleware", "app.router"):
        lg = logging.getLogger(name)
        if not lg.handlers:
            lg.addHandler(handler)
        lg.setLevel(logging.INFO)
        lg.propagate = True  # allow pytest caplog to capture records

    # Suppress uvicorn's access log — the middleware already logs richer
    # request/response data in the unified format.
    logging.getLogger("uvicorn.access").disabled = True
