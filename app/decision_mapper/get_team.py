from app.decision_mapper.operation import Operation

class GetTeamOperation(Operation):
    required_fields = ("teamId",)
    provider_method = "get_team"

    def normalize(self, raw: dict) -> dict:
        if not isinstance(raw, dict):
            return {}
        return {
            "teamId": raw.get("teamId"),
            "teamName": raw.get("teamName"),
            "shortName": raw.get("shortName"),
            "teamIconUrl": raw.get("teamIconUrl"),
        }
