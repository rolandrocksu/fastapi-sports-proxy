from typing import Any


# ---------- Normalizers ----------

def _normalize_leagues(raw: list) -> list:
    return [
        {
            "leagueId": item.get("leagueId"),
            "leagueName": item.get("leagueName"),
            "leagueShortcut": item.get("leagueShortcut"),
            "leagueSeason": item.get("leagueSeason"),
        }
        for item in (raw if isinstance(raw, list) else [])
    ]


def _normalize_matches(raw: list) -> list:
    results = []
    for item in (raw if isinstance(raw, list) else []):
        goals = item.get("goals") or []
        results.append(
            {
                "matchId": item.get("matchID"),
                "matchDateTime": item.get("matchDateTimeUTC"),
                "leagueName": item.get("leagueName"),
                "team1": item.get("team1", {}).get("teamName"),
                "team2": item.get("team2", {}).get("teamName"),
                "scoreTeam1": goals[-1].get("scoreTeam1") if goals else None,
                "scoreTeam2": goals[-1].get("scoreTeam2") if goals else None,
                "isFinished": item.get("matchIsFinished"),
            }
        )
    return results


def _normalize_team(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    return {
        "teamId": raw.get("teamId"),
        "teamName": raw.get("teamName"),
        "shortName": raw.get("shortName"),
        "teamIconUrl": raw.get("teamIconUrl"),
    }


def _normalize_match(raw: dict) -> dict:
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


# ---------- Operation registry ----------

OPERATIONS: dict[str, dict] = {
    "ListLeagues": {
        "required": [],
        "method": "list_leagues",
        "normalizer": _normalize_leagues,
    },
    "GetLeagueMatches": {
        "required": ["leagueShortcut", "leagueSeason"],
        "method": "get_league_matches",
        "normalizer": _normalize_matches,
    },
    "GetTeam": {
        "required": ["teamId"],
        "method": "get_team",
        "normalizer": _normalize_team,
    },
    "GetMatch": {
        "required": ["matchId"],
        "method": "get_match",
        "normalizer": _normalize_match,
    },
}


def validate_payload(operation_type: str, payload: dict) -> list[str]:
    """Returns list of missing required fields (empty = valid)."""
    spec = OPERATIONS[operation_type]
    return [f for f in spec["required"] if f not in payload or payload[f] is None]


async def dispatch(operation_type: str, payload: dict, provider) -> tuple[Any, int, str]:
    """
    Calls the correct provider method and normalizes the response.
    Returns (normalized_data, upstream_status_code, target_url).
    """
    spec = OPERATIONS[operation_type]
    method = getattr(provider, spec["method"])
    upstream_status, raw, url = await method(payload)
    normalized = spec["normalizer"](raw)
    return normalized, upstream_status, url
