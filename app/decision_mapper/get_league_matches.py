from app.decision_mapper.operation import Operation


class GetLeagueMatchesOperation(Operation):
    required_fields = ("leagueShortcut", "leagueSeason")
    provider_method = "get_league_matches"

    def normalize(self, raw: list) -> list:
        result = []
        for item in (raw if isinstance(raw, list) else []):
            goals = item.get("goals") or []
            result.append({
                "matchId": item.get("matchID"),
                "matchDateTime": item.get("matchDateTimeUTC"),
                "leagueName": item.get("leagueName"),
                "team1": item.get("team1", {}).get("teamName"),
                "team2": item.get("team2", {}).get("teamName"),
                "scoreTeam1": goals[-1].get("scoreTeam1") if goals else None,
                "scoreTeam2": goals[-1].get("scoreTeam2") if goals else None,
                "isFinished": item.get("matchIsFinished"),
            })
        return result
