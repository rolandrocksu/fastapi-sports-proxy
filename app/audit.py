import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Structured audit logger for the proxy lifecycle.

    Each proxy request creates one AuditLogger instance that emits a sequence
    of log records, all correlated by ``requestId`` (carried in the log
    envelope via ``extra``).

    Lifecycle events emitted:
      1. ``validation``       — pass/fail with missing field details
      2. ``upstream_call``    — provider name + target URL (no secrets)
      3. ``upstream_response``— upstream HTTP status + latency
      4. ``outcome``          — final success or error with code + total latency

    Every record also contains ``operationType`` in the JSON body.  The
    ``requestId`` and ``timestamp`` live in the log envelope (handled by the
    formatter) and are NOT duplicated inside the JSON payload.
    """

    def __init__(self, request_id: str, operation_type: str) -> None:
        self.request_id = request_id
        self.operation_type = operation_type
        self._start = time.monotonic()

    # ── internal ──────────────────────────────────────────────────────

    def _emit(self, record: dict) -> None:
        """Write a single JSON body, attaching operationType.

        requestId and timestamp are carried by the log envelope (formatter),
        not inside the JSON payload.
        """
        record["operationType"] = self.operation_type
        logger.info(json.dumps(record), extra={"request_id": self.request_id})

    # ── validation ────────────────────────────────────────────────────

    def validation_passed(self) -> None:
        self._emit({"event": "validation", "outcome": "pass"})

    def validation_failed(self, missing_fields: list[str]) -> None:
        self._emit(
            {"event": "validation", "outcome": "fail", "missingFields": missing_fields}
        )

    # ── upstream ──────────────────────────────────────────────────────

    def upstream_call(self, provider: str, url: str) -> None:
        self._emit({"event": "upstream_call", "provider": provider, "targetUrl": url})

    def upstream_response(self, provider: str, url: str, status: int) -> None:
        latency_ms = round((time.monotonic() - self._start) * 1000, 2)
        self._emit(
            {
                "event": "upstream_response",
                "provider": provider,
                "targetUrl": url,
                "upstreamStatus": status,
                "latencyMs": latency_ms,
            }
        )

    # ── outcome ───────────────────────────────────────────────────────

    def success(self) -> None:
        latency_ms = round((time.monotonic() - self._start) * 1000, 2)
        self._emit(
            {"event": "outcome", "result": "success", "totalLatencyMs": latency_ms}
        )

    def error(self, code: str, detail: Any = None) -> None:
        latency_ms = round((time.monotonic() - self._start) * 1000, 2)
        self._emit(
            {
                "event": "outcome",
                "result": "error",
                "errorCode": code,
                "detail": str(detail),
                "totalLatencyMs": latency_ms,
            }
        )
