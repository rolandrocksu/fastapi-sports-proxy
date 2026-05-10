from typing import Any

from app.decision_mapper.operation import Operation
from app.providers.base import SportsProvider


class DecisionMapper:
    """
    Routes operationType strings to Operation instances.

    The router talks only to this class — it never knows which concrete
    Operation is handling a request or how normalization works.
    """

    def __init__(self, operations: dict[str, Operation]) -> None:
        self._operations = operations

    def is_known(self, operation_type: str) -> bool:
        return operation_type in self._operations

    def missing_fields(self, operation_type: str, payload: dict) -> list[str]:
        return self._operations[operation_type].missing_fields(payload)

    async def dispatch(
        self, operation_type: str, payload: dict, provider: SportsProvider
    ) -> tuple[Any, int, str]:
        return await self._operations[operation_type].execute(payload, provider)
