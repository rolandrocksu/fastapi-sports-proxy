from abc import ABC, abstractmethod
from typing import Any

from app.providers.base import SportsProvider


class Operation(ABC):
    """
    Defines the contract for a single proxy operation.

    Each subclass declares:
      required_fields  — payload keys that must be present and non-None
      provider_method  — name of the SportsProvider method to call
      normalize()      — transforms raw provider response to stable output schema
    """

    required_fields: tuple[str, ...] = ()
    provider_method: str

    def missing_fields(self, payload: dict) -> list[str]:
        return [f for f in self.required_fields if f not in payload or payload[f] is None]

    @abstractmethod
    def normalize(self, raw: Any) -> Any: ...

    async def execute(self, payload: dict, provider: SportsProvider) -> tuple[Any, int, str]:
        method = getattr(provider, self.provider_method)
        status, raw, url = await method(payload)
        return self.normalize(raw), status, url
