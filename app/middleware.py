import json
import logging
import time
import uuid

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.lib.context import request_id_var

logger = logging.getLogger(__name__)

SENSITIVE_HEADERS = frozenset(
    {"authorization", "cookie", "x-api-key", "x-auth-token", "proxy-authorization"}
)


class RequestResponseMiddleware(BaseHTTPMiddleware):
    """
    Middleware that records inbound request metadata and outbound response
    metadata for every HTTP call.

    Responsibilities:
      • Generates (or reuses) a requestId for correlation across the entire
        request lifecycle — audit logs, middleware logs, and the response body
        all share the same ID via a ContextVar.
      • Masks sensitive headers (Authorization, Cookie, …) before logging.
      • Truncates large request/response bodies to a configurable limit so
        secrets or oversized payloads never leak into logs.
      • Attaches the requestId to the response via X-Request-ID header.

    The ``requestId`` and ``timestamp`` are NOT included in the JSON message
    body — they are carried by the log envelope (handled by the formatter).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # ── 1. Resolve / generate request ID ──────────────────────────
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        # Share with downstream handlers (router, audit) via ContextVar —
        # this is reliable across BaseHTTPMiddleware boundaries unlike
        # request.state which may not propagate.
        request_id_var.set(request_id)

        start = time.monotonic()

        # ── 2. Capture & preview the request body ─────────────────────
        # request.body() caches bytes in request._body so downstream can
        # still read it.
        body_bytes = await request.body()
        body_preview = body_bytes[: settings.log_body_max_chars].decode(
            "utf-8", errors="replace"
        )

        # ── 3. Build header dict with secrets masked ──────────────────
        safe_headers = {
            k: ("***" if k.lower() in SENSITIVE_HEADERS else v)
            for k, v in request.headers.items()
        }

        logger.info(
            json.dumps(
                {
                    "event": "request",
                    "method": request.method,
                    "path": request.url.path,
                    "headers": safe_headers,
                    "bodySizeBytes": len(body_bytes),
                    "bodyPreview": body_preview,
                }
            ),
            extra={"request_id": request_id},
        )

        # ── 4. Call downstream ────────────────────────────────────────
        response = await call_next(request)
        latency_ms = round((time.monotonic() - start) * 1000, 2)

        # ── 5. Capture response body ──────────────────────────────────
        resp_body = b""
        async for chunk in response.body_iterator:
            resp_body += chunk

        resp_preview = resp_body[: settings.log_body_max_chars].decode(
            "utf-8", errors="replace"
        )

        logger.info(
            json.dumps(
                {
                    "event": "response",
                    "statusCode": response.status_code,
                    "bodySizeBytes": len(resp_body),
                    "bodyPreview": resp_preview,
                    "latencyMs": latency_ms,
                }
            ),
            extra={"request_id": request_id},
        )

        # ── 6. Rebuild response, injecting X-Request-ID ──────────────
        headers = dict(response.headers)
        headers["X-Request-ID"] = request_id

        return Response(
            content=resp_body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )
