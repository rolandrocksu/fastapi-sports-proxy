from app.providers.base import SportsProvider
from app.api_clients.openliga_client import OpenLigaClient, BASE_URL


class OpenLigaAdapter(SportsProvider):
    """
    Adapter that makes OpenLigaClient conform to the SportsProvider interface.

    Wraps the incompatible OpenLigaClient (Service) and translates each
    SportsProvider method call into the corresponding OpenLiga API call,
    converting the payload dict into the positional arguments the client expects.
    """

    def __init__(self, client: OpenLigaClient) -> None:
        self._client = client

    async def list_leagues(self, payload: dict) -> tuple[int, list, str]:
        status, data = await self._client.get_available_leagues()
        return status, data, f"{BASE_URL}/getavailableleagues"

    async def get_league_matches(self, payload: dict) -> tuple[int, list, str]:
        shortcut = payload["leagueShortcut"]
        season = payload["leagueSeason"]
        status, data = await self._client.get_match_data(shortcut, season)
        return status, data, f"{BASE_URL}/getmatchdata/{shortcut}/{season}"

    async def get_team(self, payload: dict) -> tuple[int, dict, str]:
        team_id = payload["teamId"]
        status, data = await self._client.get_team_by(team_id)
        return status, data, f"{BASE_URL}/getteamby/{team_id}"

    async def get_match(self, payload: dict) -> tuple[int, dict, str]:
        match_id = payload["matchId"]
        status, data = await self._client.get_match_by_id(match_id)
        return status, data, f"{BASE_URL}/getmatchbyid/{match_id}"

    async def close(self) -> None:
        await self._client.close()
