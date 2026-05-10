import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class AuditLogger:
    def __init__(self, request_id: str, operation_type: str) -> None:
        self.request_id = request_id
        self.operation_type = operation_type
        self._start = time.monotonic()

    def _emit(self, record: dict) -> None:
        record["requestId"] = self.request_id
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
        record["operationType"] = self.operation_type
        logger.info(json.dumps(record))

    def validation_passed(self) -> None:
        self._emit({"event": "validation", "outcome": "pass"})

    def validation_failed(self, missing_fields: list[str]) -> None:
        self._emit({"event": "validation", "outcome": "fail", "missingFields": missing_fields})

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

    def success(self) -> None:
        latency_ms = round((time.monotonic() - self._start) * 1000, 2)
        self._emit({"event": "outcome", "result": "success", "totalLatencyMs": latency_ms})

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
