from app.decision_mapper.operation import Operation

class ListLeaguesOperation(Operation):
    required_fields = ()
    provider_method = "list_leagues"

    def normalize(self, raw: list) -> list:
        return [
            {
                "leagueId": item.get("leagueId"),
                "leagueName": item.get("leagueName"),
                "leagueShortcut": item.get("leagueShortcut"),
                "leagueSeason": item.get("leagueSeason"),
            }
            for item in (raw if isinstance(raw, list) else [])
        ]
