import asyncio
import time


class RateLimiter:
    """Token bucket rate limiter (per-process)."""

    def __init__(self, rps: float) -> None:
        self._rps = rps
        self._tokens = rps
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._rps, self._tokens + elapsed * self._rps)
            self._last_refill = now

            if self._tokens >= 1:
                self._tokens -= 1
                return

            wait = (1 - self._tokens) / self._rps

        await asyncio.sleep(wait)
        await self.acquire()
