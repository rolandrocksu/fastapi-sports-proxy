"""
Unit tests for providers/openliga.py.

Covers:
- RateLimiter: token bucket allows and throttles requests
- OpenLigaProvider._get: success, retry on 5xx, retry on 429, exhausted retries,
  timeout retry, final 5xx returned (not retried) on last attempt
- URL construction for each of the four provider methods
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.providers.openliga import OpenLigaProvider, BASE_URL
from app.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def mock_response(status_code: int, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    return resp


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    async def test_allows_first_request_immediately(self):
        limiter = RateLimiter(rps=10)
        # Should not sleep — just complete
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await limiter.acquire()
        mock_sleep.assert_not_called()

    async def test_throttles_when_tokens_exhausted(self):
        limiter = RateLimiter(rps=1)
        limiter._tokens = 0  # empty bucket

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # Break the recursion after one sleep by refilling tokens
            async def fake_sleep(duration):
                limiter._tokens = limiter._rps  # simulate time passing

            mock_sleep.side_effect = fake_sleep
            await limiter.acquire()

        mock_sleep.assert_called_once()

    async def test_token_is_consumed_after_acquire(self):
        limiter = RateLimiter(rps=5)
        initial = limiter._tokens
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await limiter.acquire()
        assert limiter._tokens < initial


# ---------------------------------------------------------------------------
# OpenLigaProvider._get
# ---------------------------------------------------------------------------

class TestOpenLigaProviderGet:
    def _make_provider(self):
        provider = OpenLigaProvider.__new__(OpenLigaProvider)
        provider._rate_limiter = AsyncMock()
        provider._rate_limiter.acquire = AsyncMock()
        return provider

    async def test_successful_200_returns_data(self):
        provider = self._make_provider()
        provider._client = AsyncMock()
        provider._client.get = AsyncMock(return_value=mock_response(200, [{"id": 1}]))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            status, data, url = await provider._get("/getavailableleagues")

        assert status == 200
        assert data == [{"id": 1}]
        assert url == f"{BASE_URL}/getavailableleagues"

    async def test_retries_once_on_500_then_succeeds(self):
        provider = self._make_provider()
        provider._client = AsyncMock()
        provider._client.get = AsyncMock(side_effect=[
            mock_response(500),
            mock_response(200, {"ok": True}),
        ])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("app.providers.openliga.settings") as mock_settings:
                mock_settings.max_retries = 3
                mock_settings.backoff_base_delay = 0.0
                mock_settings.backoff_max_delay = 1.0
                status, data, _ = await provider._get("/path")

        assert status == 200
        assert provider._client.get.call_count == 2

    async def test_retries_on_429(self):
        provider = self._make_provider()
        provider._client = AsyncMock()
        provider._client.get = AsyncMock(side_effect=[
            mock_response(429),
            mock_response(200, {"ok": True}),
        ])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("app.providers.openliga.settings") as mock_settings:
                mock_settings.max_retries = 3
                mock_settings.backoff_base_delay = 0.0
                mock_settings.backoff_max_delay = 1.0
                status, _, _ = await provider._get("/path")

        assert status == 200
        assert provider._client.get.call_count == 2

    async def test_raises_after_max_retries_all_5xx(self):
        provider = self._make_provider()
        provider._client = AsyncMock()
        provider._client.get = AsyncMock(return_value=mock_response(503))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("app.providers.openliga.settings") as mock_settings:
                mock_settings.max_retries = 2
                mock_settings.backoff_base_delay = 0.0
                mock_settings.backoff_max_delay = 1.0
                with pytest.raises(RuntimeError, match="Upstream failed"):
                    await provider._get("/path")

        assert provider._client.get.call_count == 3  # attempts 0, 1, 2

    async def test_raises_after_max_retries_on_timeout(self):
        import httpx
        provider = self._make_provider()
        provider._client = AsyncMock()
        provider._client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("app.providers.openliga.settings") as mock_settings:
                mock_settings.max_retries = 2
                mock_settings.backoff_base_delay = 0.0
                mock_settings.backoff_max_delay = 1.0
                with pytest.raises(RuntimeError, match="Upstream failed"):
                    await provider._get("/path")

    async def test_raises_when_exhausted_on_final_retryable_5xx(self):
        """Exhausting all retries on a retryable 5xx must raise (not silently return)."""
        provider = self._make_provider()
        provider._client = AsyncMock()
        provider._client.get = AsyncMock(side_effect=[
            mock_response(503),
            mock_response(503),
        ])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("app.providers.openliga.settings") as mock_settings:
                mock_settings.max_retries = 1  # 2 total attempts
                mock_settings.backoff_base_delay = 0.0
                mock_settings.backoff_max_delay = 1.0
                with pytest.raises(RuntimeError, match="Upstream failed"):
                    await provider._get("/path")

    async def test_backoff_sleep_is_called_between_retries(self):
        provider = self._make_provider()
        provider._client = AsyncMock()
        provider._client.get = AsyncMock(side_effect=[
            mock_response(503),
            mock_response(200, {}),
        ])

        sleep_calls = []

        async def capture_sleep(duration):
            sleep_calls.append(duration)

        with patch("asyncio.sleep", side_effect=capture_sleep):
            with patch("app.providers.openliga.settings") as mock_settings:
                mock_settings.max_retries = 3
                mock_settings.backoff_base_delay = 1.0
                mock_settings.backoff_max_delay = 60.0
                await provider._get("/path")

        # Sleep should have been called once (before attempt 1)
        assert len(sleep_calls) == 1
        # With base_delay=1.0 and attempt=1: delay = 1.0 * 2^0 + jitter = 1.0 + [0, 0.5)
        assert 1.0 <= sleep_calls[0] <= 1.5


# ---------------------------------------------------------------------------
# URL construction per method
# ---------------------------------------------------------------------------

class TestOpenLigaURLConstruction:
    def _make_provider_with_mock_get(self):
        provider = OpenLigaProvider.__new__(OpenLigaProvider)
        provider._rate_limiter = AsyncMock()
        provider._rate_limiter.acquire = AsyncMock()
        provider._get = AsyncMock(return_value=(200, [], BASE_URL + "/path"))
        return provider

    async def test_list_leagues_calls_correct_path(self):
        provider = self._make_provider_with_mock_get()
        provider._get.return_value = (200, [], f"{BASE_URL}/getavailableleagues")
        await provider.list_leagues({})
        provider._get.assert_called_once_with("/getavailableleagues")

    async def test_get_league_matches_builds_path_from_payload(self):
        provider = self._make_provider_with_mock_get()
        await provider.get_league_matches({"leagueShortcut": "bl1", "leagueSeason": "2023"})
        provider._get.assert_called_once_with("/getmatchdata/bl1/2023")

    async def test_get_team_builds_path_from_team_id(self):
        provider = self._make_provider_with_mock_get()
        await provider.get_team({"teamId": 40})
        provider._get.assert_called_once_with("/getteamby/40")

    async def test_get_match_builds_path_from_match_id(self):
        provider = self._make_provider_with_mock_get()
        await provider.get_match({"matchId": 61588})
        provider._get.assert_called_once_with("/getmatchbyid/61588")
