from abc import ABC, abstractmethod


class SportsProvider(ABC):
    @abstractmethod
    async def list_leagues(self, payload: dict) -> tuple[int, list, str]:
        ...

    @abstractmethod
    async def get_league_matches(self, payload: dict) -> tuple[int, list, str]:
        ...

    @abstractmethod
    async def get_team(self, payload: dict) -> tuple[int, dict, str]:
        ...

    @abstractmethod
    async def get_match(self, payload: dict) -> tuple[int, dict, str]:
        ...
