from pydantic import BaseModel
from typing import Any


class ProxyRequest(BaseModel):
    operationType: str
    payload: dict[str, Any] = {}


class ProxyResponse(BaseModel):
    requestId: str
    operationType: str
    data: Any


class ErrorResponse(BaseModel):
    error: str
    detail: Any = None
