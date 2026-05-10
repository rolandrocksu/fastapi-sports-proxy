from app.decision_mapper.operation import Operation


class GetMatchOperation(Operation):
    required_fields = ("matchId",)
    provider_method = "get_match"

    def normalize(self, raw: dict) -> dict:
        if not isinstance(raw, dict):
            return {}
        goals = raw.get("goals") or []
        return {
            "matchId": raw.get("matchID"),
            "matchDateTime": raw.get("matchDateTimeUTC"),
            "leagueName": raw.get("leagueName"),
            "team1": raw.get("team1", {}).get("teamName"),
            "team2": raw.get("team2", {}).get("teamName"),
            "scoreTeam1": goals[-1].get("scoreTeam1") if goals else None,
            "scoreTeam2": goals[-1].get("scoreTeam2") if goals else None,
            "isFinished": raw.get("matchIsFinished"),
            "location": raw.get("location", {}).get("locationCity") if raw.get("location") else None,
        }
