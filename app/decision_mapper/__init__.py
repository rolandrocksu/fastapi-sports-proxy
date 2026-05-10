from app.decision_mapper.mapper import DecisionMapper
from app.decision_mapper.operation import Operation
from app.decision_mapper.list_leagues import ListLeaguesOperation
from app.decision_mapper.get_league_matches import GetLeagueMatchesOperation
from app.decision_mapper.get_team import GetTeamOperation
from app.decision_mapper.get_match import GetMatchOperation

# Module-level singleton — imported by router
mapper = DecisionMapper({
    "ListLeagues": ListLeaguesOperation(),
    "GetLeagueMatches": GetLeagueMatchesOperation(),
    "GetTeam": GetTeamOperation(),
    "GetMatch": GetMatchOperation(),
})

__all__ = [
    "DecisionMapper",
    "Operation",
    "ListLeaguesOperation",
    "GetLeagueMatchesOperation",
    "GetTeamOperation",
    "GetMatchOperation",
    "mapper",
]
