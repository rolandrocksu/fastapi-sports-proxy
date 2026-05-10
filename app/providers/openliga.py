import asyncio
import random
import httpx

from app.providers.base import SportsProvider
from app.rate_limiter import RateLimiter
from app.config import settings

BASE_URL = "https://api.openligadb.de"

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class OpenLigaProvider(SportsProvider):
    def __init__(self):
        self._rate_limiter = RateLimiter(rps=settings.rate_limit_rps)
        self._client = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)

    async def _get(self, path: str) -> tuple[int, any, str]:
        """Execute GET with rate limiting and exponential backoff. Returns (status, body, url)."""
        url = f"{BASE_URL}{path}"
        await self._rate_limiter.acquire()

        last_exc = None
        for attempt in range(settings.max_retries + 1):
            if attempt > 0:
                delay = min(
                    settings.backoff_base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5),
                    settings.backoff_max_delay,
                )
                await asyncio.sleep(delay)

            try:
                resp = await self._client.get(path)
                if resp.status_code in RETRYABLE_STATUS:
                    last_exc = Exception(f"HTTP {resp.status_code}")
                    if attempt < settings.max_retries:
                        continue
                    break  # exhausted retries on 5xx/429 → raise below
                return resp.status_code, resp.json(), url
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt == settings.max_retries:
                    break

        raise RuntimeError(f"Upstream failed after {settings.max_retries + 1} attempts: {last_exc}") from last_exc

    async def list_leagues(self, payload: dict) -> tuple[int, list, str]:
        status, data, url = await self._get("/getavailableleagues")
        return status, data, url

    async def get_league_matches(self, payload: dict) -> tuple[int, list, str]:
        shortcut = payload["leagueShortcut"]
        season = payload["leagueSeason"]
        status, data, url = await self._get(f"/getmatchdata/{shortcut}/{season}")
        return status, data, url

    async def get_team(self, payload: dict) -> tuple[int, dict, str]:
        team_id = payload["teamId"]
        status, data, url = await self._get(f"/getteamby/{team_id}")
        return status, data, url

    async def get_match(self, payload: dict) -> tuple[int, dict, str]:
        match_id = payload["matchId"]
        status, data, url = await self._get(f"/getmatchbyid/{match_id}")
        return status, data, url

    async def close(self):
        await self._client.aclose()
