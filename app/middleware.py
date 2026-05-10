import json
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger(__name__)

SENSITIVE_HEADERS = frozenset(
    {"authorization", "cookie", "x-api-key", "x-auth-token", "proxy-authorization"}
)


class RequestResponseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start = time.monotonic()

        # request.body() caches bytes in request._body so downstream can still read it
        body_bytes = await request.body()
        body_preview = body_bytes[: settings.log_body_max_chars].decode("utf-8", errors="replace")

        safe_headers = {
            k: ("***" if k.lower() in SENSITIVE_HEADERS else v)
            for k, v in request.headers.items()
        }

        logger.info(json.dumps({
            "event": "request",
            "requestId": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": request.method,
            "path": request.url.path,
            "headers": safe_headers,
            "bodySizeBytes": len(body_bytes),
            "bodyPreview": body_preview,
        }))

        response = await call_next(request)
        latency_ms = round((time.monotonic() - start) * 1000, 2)

        resp_body = b""
        async for chunk in response.body_iterator:
            resp_body += chunk

        logger.info(json.dumps({
            "event": "response",
            "requestId": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "statusCode": response.status_code,
            "bodySizeBytes": len(resp_body),
            "latencyMs": latency_ms,
        }))

        return Response(
            content=resp_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
