"""
Unit tests for decision_mapper.py.

Structure mirrors the class hierarchy:

  TestOperationBase              — shared contract: missing_fields + execute
  TestListLeaguesOperation       — normalize()
  TestGetLeagueMatchesOperation  — required_fields + normalize()
  TestGetTeamOperation           — required_fields + normalize()
  TestGetMatchOperation          — required_fields + normalize()
  TestDecisionMapper             — is_known, missing_fields, dispatch
"""

import pytest
from unittest.mock import AsyncMock

from app.decision_mapper import (
    GetLeagueMatchesOperation,
    GetMatchOperation,
    GetTeamOperation,
    ListLeaguesOperation,
    Operation,
    mapper,
)


# ---------------------------------------------------------------------------
# TestOperationBase — contract shared by all operations
# ---------------------------------------------------------------------------

class TestOperationBase:
    """Uses ListLeaguesOperation as a concrete stand-in for the base behaviour."""

    def test_operation_is_abstract(self):
        with pytest.raises(TypeError):
            Operation()  # type: ignore[abstract]

    def test_missing_fields_returns_empty_when_all_present(self):
        op = GetTeamOperation()
        assert op.missing_fields({"teamId": 1}) == []

    def test_missing_fields_returns_field_names_when_absent(self):
        op = GetLeagueMatchesOperation()
        missing = op.missing_fields({"leagueShortcut": "bl1"})
        assert missing == ["leagueSeason"]

    def test_missing_fields_treats_none_as_missing(self):
        op = GetTeamOperation()
        assert "teamId" in op.missing_fields({"teamId": None})

    def test_missing_fields_allows_falsy_non_none(self):
        op = GetTeamOperation()
        assert op.missing_fields({"teamId": 0}) == []

    async def test_execute_calls_provider_method_and_normalizes(self):
        op = ListLeaguesOperation()
        provider = AsyncMock()
        raw = [{"leagueId": 1, "leagueName": "BL", "leagueShortcut": "bl1", "leagueSeason": "2023"}]
        provider.list_leagues.return_value = (200, raw, "https://url")

        data, status, url = await op.execute({}, provider)

        provider.list_leagues.assert_called_once_with({})
        assert status == 200
        assert data[0]["leagueId"] == 1

    async def test_execute_returns_normalized_not_raw(self):
        op = ListLeaguesOperation()
        provider = AsyncMock()
        raw = [{"leagueId": 5, "leagueName": "T", "leagueShortcut": "tl", "leagueSeason": "2024", "secret": "X"}]
        provider.list_leagues.return_value = (200, raw, "url")

        data, _, _ = await op.execute({}, provider)

        assert "secret" not in data[0]


# ---------------------------------------------------------------------------
# TestListLeaguesOperation
# ---------------------------------------------------------------------------

class TestListLeaguesOperation:
    op = ListLeaguesOperation()

    def test_required_fields_is_empty(self):
        assert self.op.required_fields == ()

    def test_provider_method(self):
        assert self.op.provider_method == "list_leagues"

    def test_normalize_extracts_expected_keys(self):
        raw = [{"leagueId": 1, "leagueName": "BL", "leagueShortcut": "bl1", "leagueSeason": "2023", "extra": "drop"}]
        result = self.op.normalize(raw)
        assert result == [{"leagueId": 1, "leagueName": "BL", "leagueShortcut": "bl1", "leagueSeason": "2023"}]

    def test_normalize_empty_list(self):
        assert self.op.normalize([]) == []

    def test_normalize_non_list_returns_empty(self):
        assert self.op.normalize(None) == []
        assert self.op.normalize({}) == []

    def test_normalize_partial_fields_become_none(self):
        result = self.op.normalize([{"leagueId": 99}])
        assert result[0]["leagueName"] is None
        assert result[0]["leagueShortcut"] is None


# ---------------------------------------------------------------------------
# TestGetLeagueMatchesOperation
# ---------------------------------------------------------------------------

class TestGetLeagueMatchesOperation:
    op = GetLeagueMatchesOperation()

    def _make_match(self, goals=None):
        return {
            "matchID": 100,
            "matchDateTimeUTC": "2023-08-18T18:30:00Z",
            "leagueName": "BL",
            "team1": {"teamName": "Bayern"},
            "team2": {"teamName": "Dortmund"},
            "matchIsFinished": True,
            "goals": goals or [],
        }

    def test_required_fields(self):
        assert set(self.op.required_fields) == {"leagueShortcut", "leagueSeason"}

    def test_provider_method(self):
        assert self.op.provider_method == "get_league_matches"

    def test_normalize_with_goals_uses_last_score(self):
        match = self._make_match(goals=[
            {"scoreTeam1": 1, "scoreTeam2": 0},
            {"scoreTeam1": 2, "scoreTeam2": 1},
        ])
        result = self.op.normalize([match])
        assert result[0]["scoreTeam1"] == 2
        assert result[0]["scoreTeam2"] == 1

    def test_normalize_no_goals_scores_are_none(self):
        result = self.op.normalize([self._make_match(goals=[])])
        assert result[0]["scoreTeam1"] is None
        assert result[0]["scoreTeam2"] is None

    def test_normalize_field_mapping(self):
        result = self.op.normalize([self._make_match()])
        assert result[0]["matchId"] == 100
        assert result[0]["team1"] == "Bayern"
        assert result[0]["isFinished"] is True

    def test_normalize_empty_returns_empty(self):
        assert self.op.normalize([]) == []

    def test_normalize_non_list_returns_empty(self):
        assert self.op.normalize(None) == []


# ---------------------------------------------------------------------------
# TestGetTeamOperation
# ---------------------------------------------------------------------------

class TestGetTeamOperation:
    op = GetTeamOperation()

    RAW = {"teamId": 40, "teamName": "FC Bayern", "shortName": "Bayern", "teamIconUrl": "https://icon", "extra": "drop"}

    def test_required_fields(self):
        assert self.op.required_fields == ("teamId",)

    def test_provider_method(self):
        assert self.op.provider_method == "get_team"

    def test_normalize_extracts_expected_keys(self):
        result = self.op.normalize(self.RAW)
        assert result == {"teamId": 40, "teamName": "FC Bayern", "shortName": "Bayern", "teamIconUrl": "https://icon"}

    def test_normalize_strips_extra_keys(self):
        assert "extra" not in self.op.normalize(self.RAW)

    def test_normalize_non_dict_returns_empty(self):
        assert self.op.normalize([]) == {}
        assert self.op.normalize(None) == {}


# ---------------------------------------------------------------------------
# TestGetMatchOperation
# ---------------------------------------------------------------------------

class TestGetMatchOperation:
    op = GetMatchOperation()

    def _make_raw(self, goals=None, location=None):
        return {
            "matchID": 61588,
            "matchDateTimeUTC": "2023-08-18T18:30:00Z",
            "leagueName": "BL",
            "team1": {"teamName": "Bayern"},
            "team2": {"teamName": "Bremen"},
            "matchIsFinished": True,
            "goals": goals if goals is not None else [],
            "location": location,
        }

    def test_required_fields(self):
        assert self.op.required_fields == ("matchId",)

    def test_provider_method(self):
        assert self.op.provider_method == "get_match"

    def test_normalize_with_goals_and_location(self):
        raw = self._make_raw(
            goals=[{"scoreTeam1": 4, "scoreTeam2": 0}],
            location={"locationCity": "München"},
        )
        result = self.op.normalize(raw)
        assert result["matchId"] == 61588
        assert result["scoreTeam1"] == 4
        assert result["location"] == "München"

    def test_normalize_no_goals_scores_are_none(self):
        result = self.op.normalize(self._make_raw())
        assert result["scoreTeam1"] is None

    def test_normalize_no_location_is_none(self):
        result = self.op.normalize(self._make_raw(location=None))
        assert result["location"] is None

    def test_normalize_non_dict_returns_empty(self):
        assert self.op.normalize(None) == {}


# ---------------------------------------------------------------------------
# TestDecisionMapper
# ---------------------------------------------------------------------------

class TestDecisionMapper:
    def test_is_known_returns_true_for_registered_operations(self):
        for op in ("ListLeagues", "GetLeagueMatches", "GetTeam", "GetMatch"):
            assert mapper.is_known(op)

    def test_is_known_returns_false_for_unknown(self):
        assert not mapper.is_known("DoSomethingWeird")

    def test_missing_fields_delegates_to_operation(self):
        assert mapper.missing_fields("GetTeam", {}) == ["teamId"]
        assert mapper.missing_fields("GetTeam", {"teamId": 1}) == []

    def test_missing_fields_for_operation_with_no_required(self):
        assert mapper.missing_fields("ListLeagues", {}) == []

    async def test_dispatch_calls_execute_on_correct_operation(self):
        provider = AsyncMock()
        provider.list_leagues.return_value = (200, [], "url")

        data, status, url = await mapper.dispatch("ListLeagues", {}, provider)

        provider.list_leagues.assert_called_once_with({})
        assert status == 200

    async def test_dispatch_normalizes_output(self):
        provider = AsyncMock()
        raw = [{"leagueId": 1, "leagueName": "T", "leagueShortcut": "t", "leagueSeason": "2024", "raw": "X"}]
        provider.list_leagues.return_value = (200, raw, "url")

        data, _, _ = await mapper.dispatch("ListLeagues", {}, provider)

        assert "raw" not in data[0]
        assert data[0]["leagueId"] == 1

    async def test_dispatch_passes_payload_to_provider(self):
        provider = AsyncMock()
        provider.get_league_matches.return_value = (200, [], "url")
        payload = {"leagueShortcut": "bl1", "leagueSeason": "2023"}

        await mapper.dispatch("GetLeagueMatches", payload, provider)

        provider.get_league_matches.assert_called_once_with(payload)

    def test_mapper_singleton_has_all_four_operations(self):
        assert isinstance(mapper._operations["ListLeagues"], ListLeaguesOperation)
        assert isinstance(mapper._operations["GetLeagueMatches"], GetLeagueMatchesOperation)
        assert isinstance(mapper._operations["GetTeam"], GetTeamOperation)
        assert isinstance(mapper._operations["GetMatch"], GetMatchOperation)
