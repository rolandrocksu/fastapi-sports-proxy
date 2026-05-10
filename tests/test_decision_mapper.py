"""
Unit tests for decision_mapper.py.

Covers:
- validate_payload: all required present, missing one, missing many, None value
- _normalize_leagues: normal data, empty list, non-list input, partial fields
- _normalize_matches: with goals, no goals, empty input
- _normalize_team: normal dict, non-dict input
- _normalize_match: with goals and location, no goals, no location, non-dict
- dispatch: correct provider method called, response normalized
"""

import pytest
from unittest.mock import AsyncMock

from app.decision_mapper import (
    validate_payload,
    dispatch,
    OPERATIONS,
    _normalize_leagues,
    _normalize_matches,
    _normalize_team,
    _normalize_match,
)


# ---------------------------------------------------------------------------
# validate_payload
# ---------------------------------------------------------------------------

class TestValidatePayload:
    def test_no_required_fields_always_passes(self):
        missing = validate_payload("ListLeagues", {})
        assert missing == []

    def test_all_required_fields_present(self):
        missing = validate_payload("GetLeagueMatches", {"leagueShortcut": "bl1", "leagueSeason": "2023"})
        assert missing == []

    def test_single_missing_field(self):
        missing = validate_payload("GetLeagueMatches", {"leagueShortcut": "bl1"})
        assert missing == ["leagueSeason"]

    def test_multiple_missing_fields(self):
        missing = validate_payload("GetLeagueMatches", {})
        assert set(missing) == {"leagueShortcut", "leagueSeason"}

    def test_none_value_treated_as_missing(self):
        missing = validate_payload("GetTeam", {"teamId": None})
        assert "teamId" in missing

    def test_zero_value_not_treated_as_missing(self):
        # 0 is falsy but is a valid teamId
        missing = validate_payload("GetTeam", {"teamId": 0})
        assert missing == []

    def test_get_match_missing_match_id(self):
        missing = validate_payload("GetMatch", {})
        assert missing == ["matchId"]


# ---------------------------------------------------------------------------
# _normalize_leagues
# ---------------------------------------------------------------------------

class TestNormalizeLeagues:
    RAW = [
        {"leagueId": 1, "leagueName": "Bundesliga", "leagueShortcut": "bl1", "leagueSeason": "2023", "extra": "ignored"},
        {"leagueId": 2, "leagueName": "2. Liga", "leagueShortcut": "bl2", "leagueSeason": "2023"},
    ]

    def test_extracts_expected_keys(self):
        result = _normalize_leagues(self.RAW)
        assert result[0] == {
            "leagueId": 1,
            "leagueName": "Bundesliga",
            "leagueShortcut": "bl1",
            "leagueSeason": "2023",
        }

    def test_strips_extra_fields(self):
        result = _normalize_leagues(self.RAW)
        assert "extra" not in result[0]

    def test_empty_list_returns_empty(self):
        assert _normalize_leagues([]) == []

    def test_non_list_input_returns_empty(self):
        assert _normalize_leagues(None) == []
        assert _normalize_leagues({}) == []

    def test_partial_fields_become_none(self):
        result = _normalize_leagues([{"leagueId": 99}])
        assert result[0]["leagueName"] is None
        assert result[0]["leagueShortcut"] is None


# ---------------------------------------------------------------------------
# _normalize_matches
# ---------------------------------------------------------------------------

class TestNormalizeMatches:
    def _make_match(self, goals=None):
        return {
            "matchID": 100,
            "matchDateTimeUTC": "2023-08-18T18:30:00Z",
            "leagueName": "Bundesliga",
            "team1": {"teamName": "Bayern"},
            "team2": {"teamName": "Dortmund"},
            "matchIsFinished": True,
            "goals": goals or [],
        }

    def test_with_goals_uses_last_goal_score(self):
        match = self._make_match(goals=[
            {"scoreTeam1": 1, "scoreTeam2": 0},
            {"scoreTeam1": 2, "scoreTeam2": 1},
        ])
        result = _normalize_matches([match])
        assert result[0]["scoreTeam1"] == 2
        assert result[0]["scoreTeam2"] == 1

    def test_without_goals_scores_are_none(self):
        result = _normalize_matches([self._make_match(goals=[])])
        assert result[0]["scoreTeam1"] is None
        assert result[0]["scoreTeam2"] is None

    def test_correct_field_mapping(self):
        result = _normalize_matches([self._make_match()])
        assert result[0]["matchId"] == 100
        assert result[0]["team1"] == "Bayern"
        assert result[0]["team2"] == "Dortmund"
        assert result[0]["isFinished"] is True

    def test_empty_input_returns_empty(self):
        assert _normalize_matches([]) == []

    def test_non_list_input_returns_empty(self):
        assert _normalize_matches(None) == []

    def test_multiple_matches(self):
        matches = [self._make_match(), self._make_match()]
        matches[1]["matchID"] = 999
        result = _normalize_matches(matches)
        assert len(result) == 2
        assert result[1]["matchId"] == 999


# ---------------------------------------------------------------------------
# _normalize_team
# ---------------------------------------------------------------------------

class TestNormalizeTeam:
    RAW = {
        "teamId": 40,
        "teamName": "FC Bayern München",
        "shortName": "Bayern",
        "teamIconUrl": "https://icon.url",
        "teamGroupName": "ignored",
    }

    def test_extracts_expected_keys(self):
        result = _normalize_team(self.RAW)
        assert result == {
            "teamId": 40,
            "teamName": "FC Bayern München",
            "shortName": "Bayern",
            "teamIconUrl": "https://icon.url",
        }

    def test_strips_extra_fields(self):
        result = _normalize_team(self.RAW)
        assert "teamGroupName" not in result

    def test_non_dict_returns_empty(self):
        assert _normalize_team([]) == {}
        assert _normalize_team(None) == {}
        assert _normalize_team("bad") == {}


# ---------------------------------------------------------------------------
# _normalize_match
# ---------------------------------------------------------------------------

class TestNormalizeMatch:
    def _make_raw(self, goals=None, location=None):
        raw = {
            "matchID": 61588,
            "matchDateTimeUTC": "2023-08-18T18:30:00Z",
            "leagueName": "Bundesliga",
            "team1": {"teamName": "Bayern"},
            "team2": {"teamName": "Bremen"},
            "matchIsFinished": True,
            "goals": goals if goals is not None else [],
            "location": location,
        }
        return raw

    def test_full_data_with_goals_and_location(self):
        raw = self._make_raw(
            goals=[{"scoreTeam1": 4, "scoreTeam2": 0}],
            location={"locationCity": "München", "locationStadium": "Allianz Arena"},
        )
        result = _normalize_match(raw)
        assert result["matchId"] == 61588
        assert result["scoreTeam1"] == 4
        assert result["scoreTeam2"] == 0
        assert result["location"] == "München"

    def test_no_goals_scores_are_none(self):
        result = _normalize_match(self._make_raw())
        assert result["scoreTeam1"] is None
        assert result["scoreTeam2"] is None

    def test_no_location_is_none(self):
        result = _normalize_match(self._make_raw(location=None))
        assert result["location"] is None

    def test_non_dict_returns_empty(self):
        assert _normalize_match([]) == {}
        assert _normalize_match(None) == {}


# ---------------------------------------------------------------------------
# dispatch (async)
# ---------------------------------------------------------------------------

class TestDispatch:
    async def test_dispatch_list_leagues_calls_correct_method(self):
        provider = AsyncMock()
        provider.list_leagues.return_value = (200, [], "https://api.openligadb.de/getavailableleagues")

        data, status, url = await dispatch("ListLeagues", {}, provider)

        provider.list_leagues.assert_called_once_with({})
        assert status == 200

    async def test_dispatch_get_league_matches(self):
        provider = AsyncMock()
        provider.get_league_matches.return_value = (200, [], "https://api.openligadb.de/getmatchdata/bl1/2023")
        payload = {"leagueShortcut": "bl1", "leagueSeason": "2023"}

        await dispatch("GetLeagueMatches", payload, provider)

        provider.get_league_matches.assert_called_once_with(payload)

    async def test_dispatch_get_team(self):
        provider = AsyncMock()
        raw = {"teamId": 40, "teamName": "Bayern", "shortName": "FCB", "teamIconUrl": "url"}
        provider.get_team.return_value = (200, raw, "https://api.openligadb.de/getteamby/40")

        data, status, url = await dispatch("GetTeam", {"teamId": 40}, provider)

        assert data["teamId"] == 40
        assert data["teamName"] == "Bayern"

    async def test_dispatch_get_match(self):
        provider = AsyncMock()
        raw = {
            "matchID": 1,
            "matchDateTimeUTC": "2023-01-01T00:00:00Z",
            "leagueName": "BL",
            "team1": {"teamName": "A"},
            "team2": {"teamName": "B"},
            "matchIsFinished": False,
            "goals": [],
            "location": None,
        }
        provider.get_match.return_value = (200, raw, "url")

        data, status, url = await dispatch("GetMatch", {"matchId": 1}, provider)

        assert data["matchId"] == 1
        assert data["team1"] == "A"

    async def test_dispatch_normalizes_response(self):
        """dispatch must run the normalizer, not return raw data."""
        provider = AsyncMock()
        raw = [{"leagueId": 5, "leagueName": "Test", "leagueShortcut": "tl", "leagueSeason": "2024", "rawField": "X"}]
        provider.list_leagues.return_value = (200, raw, "url")

        data, _, _ = await dispatch("ListLeagues", {}, provider)

        assert "rawField" not in data[0]
        assert data[0]["leagueId"] == 5

    async def test_dispatch_returns_upstream_status_and_url(self):
        provider = AsyncMock()
        provider.list_leagues.return_value = (200, [], "https://test-url")

        _, status, url = await dispatch("ListLeagues", {}, provider)

        assert status == 200
        assert url == "https://test-url"
