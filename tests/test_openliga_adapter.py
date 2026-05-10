"""
Unit tests for providers/openliga.py.

Structure mirrors the Adapter pattern:

  TestRateLimiter          — token bucket (app/rate_limiter.py)
  TestOpenLigaClient       — Service: HTTP transport, retry/backoff logic
  TestOpenLigaAdapter      — Adapter: payload translation, URL construction,
                             delegation to the wrapped OpenLigaClient
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.openliga import OpenLigaAdapter
from app.api_clients.openliga_client import OpenLigaClient, BASE_URL
from app.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def mock_response(status_code: int, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    return resp


def make_client() -> OpenLigaClient:
    """OpenLigaClient with mocked internals (no real HTTP or rate limiting)."""
    client = OpenLigaClient.__new__(OpenLigaClient)
    client._rate_limiter = AsyncMock()
    client._rate_limiter.acquire = AsyncMock()
    client._http = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    async def test_allows_first_request_immediately(self):
        limiter = RateLimiter(rps=10)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await limiter.acquire()
        mock_sleep.assert_not_called()

    async def test_throttles_when_tokens_exhausted(self):
        limiter = RateLimiter(rps=1)
        limiter._tokens = 0

        async def fake_sleep(duration):
            limiter._tokens = limiter._rps  # simulate time refilling bucket

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = fake_sleep
            await limiter.acquire()

        mock_sleep.assert_called_once()

    async def test_token_consumed_after_acquire(self):
        limiter = RateLimiter(rps=5)
        initial = limiter._tokens
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await limiter.acquire()
        assert limiter._tokens < initial


# ---------------------------------------------------------------------------
# OpenLigaClient — Service (HTTP transport + retry/backoff)
# ---------------------------------------------------------------------------

class TestOpenLigaClient:
    """
    Tests the Service in isolation.
    Verifies transport behaviour: success path, retries, backoff, and
    exhausted-retry error raising. Does NOT know about SportsProvider.
    """

    async def test_successful_200_returns_status_and_data(self):
        client = make_client()
        client._http.get = AsyncMock(return_value=mock_response(200, [{"id": 1}]))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            status, data = await client._get("/getavailableleagues")

        assert status == 200
        assert data == [{"id": 1}]

    async def test_retries_on_500_then_succeeds(self):
        client = make_client()
        client._http.get = AsyncMock(side_effect=[
            mock_response(500),
            mock_response(200, {"ok": True}),
        ])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("app.api_clients.openliga_client.settings") as s:
                s.max_retries = 3
                s.backoff_base_delay = 0.0
                s.backoff_max_delay = 1.0
                status, _ = await client._get("/path")

        assert status == 200
        assert client._http.get.call_count == 2

    async def test_retries_on_429(self):
        client = make_client()
        client._http.get = AsyncMock(side_effect=[
            mock_response(429),
            mock_response(200, {}),
        ])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("app.api_clients.openliga_client.settings") as s:
                s.max_retries = 3
                s.backoff_base_delay = 0.0
                s.backoff_max_delay = 1.0
                status, _ = await client._get("/path")

        assert status == 200
        assert client._http.get.call_count == 2

    async def test_raises_after_all_retries_return_5xx(self):
        client = make_client()
        client._http.get = AsyncMock(return_value=mock_response(503))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("app.api_clients.openliga_client.settings") as s:
                s.max_retries = 2
                s.backoff_base_delay = 0.0
                s.backoff_max_delay = 1.0
                with pytest.raises(RuntimeError, match="Upstream failed"):
                    await client._get("/path")

        assert client._http.get.call_count == 3  # attempts 0, 1, 2

    async def test_raises_after_all_retries_timeout(self):
        import httpx
        client = make_client()
        client._http.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("app.api_clients.openliga_client.settings") as s:
                s.max_retries = 2
                s.backoff_base_delay = 0.0
                s.backoff_max_delay = 1.0
                with pytest.raises(RuntimeError, match="Upstream failed"):
                    await client._get("/path")

    async def test_raises_when_last_attempt_is_retryable_5xx(self):
        client = make_client()
        client._http.get = AsyncMock(side_effect=[mock_response(503), mock_response(503)])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("app.api_clients.openliga_client.settings") as s:
                s.max_retries = 1
                s.backoff_base_delay = 0.0
                s.backoff_max_delay = 1.0
                with pytest.raises(RuntimeError, match="Upstream failed"):
                    await client._get("/path")

    async def test_backoff_delay_grows_exponentially(self):
        client = make_client()
        client._http.get = AsyncMock(side_effect=[
            mock_response(503),
            mock_response(200, {}),
        ])

        sleep_calls = []

        async def capture(duration):
            sleep_calls.append(duration)

        with patch("asyncio.sleep", side_effect=capture):
            with patch("app.api_clients.openliga_client.settings") as s:
                s.max_retries = 3
                s.backoff_base_delay = 1.0
                s.backoff_max_delay = 60.0
                await client._get("/path")

        assert len(sleep_calls) == 1
        # attempt 1: delay = 1.0 * 2^0 + jitter ∈ [1.0, 1.5)
        assert 1.0 <= sleep_calls[0] <= 1.5

    async def test_public_methods_call_correct_paths(self):
        """Each public method on the client hits the right OpenLiga URL."""
        client = make_client()
        client._get = AsyncMock(return_value=(200, {}))

        await client.get_available_leagues()
        client._get.assert_called_with("/getavailableleagues")

        await client.get_match_data("bl1", "2023")
        client._get.assert_called_with("/getmatchdata/bl1/2023")

        await client.get_team_by(40)
        client._get.assert_called_with("/getteamby/40")

        await client.get_match_by_id(61588)
        client._get.assert_called_with("/getmatchbyid/61588")


# ---------------------------------------------------------------------------
# OpenLigaAdapter — Adapter (wraps OpenLigaClient, implements SportsProvider)
# ---------------------------------------------------------------------------

class TestOpenLigaAdapter:
    """
    Tests the Adapter in isolation using a mocked OpenLigaClient (Service).

    Verifies that the adapter:
    - Translates each SportsProvider method into the correct client method
    - Extracts the right fields from the payload dict
    - Returns the correct (status, data, url) tuple expected by the client interface
    """

    def _make_adapter(self) -> tuple[OpenLigaAdapter, AsyncMock]:
        mock_client = AsyncMock(spec=OpenLigaClient)
        return OpenLigaAdapter(mock_client), mock_client

    async def test_list_leagues_delegates_to_get_available_leagues(self):
        adapter, client = self._make_adapter()
        client.get_available_leagues.return_value = (200, [{"leagueId": 1}])

        status, data, url = await adapter.list_leagues({})

        client.get_available_leagues.assert_called_once_with()
        assert status == 200
        assert url == f"{BASE_URL}/getavailableleagues"

    async def test_get_league_matches_unpacks_payload_into_positional_args(self):
        adapter, client = self._make_adapter()
        client.get_match_data.return_value = (200, [])

        status, _, url = await adapter.get_league_matches(
            {"leagueShortcut": "bl1", "leagueSeason": "2023"}
        )

        client.get_match_data.assert_called_once_with("bl1", "2023")
        assert url == f"{BASE_URL}/getmatchdata/bl1/2023"

    async def test_get_team_unpacks_team_id_from_payload(self):
        adapter, client = self._make_adapter()
        client.get_team_by.return_value = (200, {"teamId": 40})

        status, data, url = await adapter.get_team({"teamId": 40})

        client.get_team_by.assert_called_once_with(40)
        assert url == f"{BASE_URL}/getteamby/40"

    async def test_get_match_unpacks_match_id_from_payload(self):
        adapter, client = self._make_adapter()
        client.get_match_by_id.return_value = (200, {"matchID": 61588})

        status, data, url = await adapter.get_match({"matchId": 61588})

        client.get_match_by_id.assert_called_once_with(61588)
        assert url == f"{BASE_URL}/getmatchbyid/61588"

    async def test_adapter_passes_through_status_and_data_unchanged(self):
        adapter, client = self._make_adapter()
        raw = [{"leagueId": 99, "leagueName": "Test"}]
        client.get_available_leagues.return_value = (200, raw)

        _, data, _ = await adapter.list_leagues({})

        assert data is raw  # adapter does NOT normalise — that's the decision_mapper's job

    async def test_close_delegates_to_client(self):
        adapter, client = self._make_adapter()
        await adapter.close()
        client.close.assert_called_once()
