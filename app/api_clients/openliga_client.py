import asyncio
import random
from typing import Any

import httpx

from app.config import settings
from app.rate_limiter import RateLimiter

BASE_URL = "https://api.openligadb.de"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class OpenLigaClient:
    """
    Thin HTTP client for the OpenLiga API.

    This is the "Service" in the Adapter pattern — it has OpenLiga's own
    interface and is incompatible with our SportsProvider contract.
    All transport concerns (httpx, rate limiting, backoff) live here.
    """

    def __init__(self, rate_limiter: RateLimiter) -> None:
        self._rate_limiter = rate_limiter
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)

    async def get_available_leagues(self) -> tuple[int, list]:
        return await self._get("/getavailableleagues")

    async def get_match_data(self, league_shortcut: str, league_season: str) -> tuple[int, list]:
        return await self._get(f"/getmatchdata/{league_shortcut}/{league_season}")

    async def get_team_by(self, team_id: int | str) -> tuple[int, dict]:
        return await self._get(f"/getteamby/{team_id}")

    async def get_match_by_id(self, match_id: int | str) -> tuple[int, dict]:
        return await self._get(f"/getmatchbyid/{match_id}")

    async def close(self) -> None:
        await self._http.aclose()

    async def _get(self, path: str) -> tuple[int, Any]:
        """Rate-limited GET with exponential backoff. Raises RuntimeError on failure."""
        await self._rate_limiter.acquire()

        last_exc: Exception | None = None
        for attempt in range(settings.max_retries + 1):
            if attempt > 0:
                delay = min(
                    settings.backoff_base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5),
                    settings.backoff_max_delay,
                )
                await asyncio.sleep(delay)

            try:
                resp = await self._http.get(path)
                if resp.status_code in RETRYABLE_STATUS:
                    last_exc = Exception(f"HTTP {resp.status_code}")
                    if attempt < settings.max_retries:
                        continue
                    break  # exhausted retries on 5xx/429 → raise below
                return resp.status_code, resp.json()
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt == settings.max_retries:
                    break

        raise RuntimeError(
            f"Upstream failed after {settings.max_retries + 1} attempts: {last_exc}"
        ) from last_exc
