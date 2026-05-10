"""
Request-scoped context variables.

ContextVars survive across async boundaries and BaseHTTPMiddleware's
internal scope copies, unlike request.state which may not propagate
reliably to downstream handlers.
"""

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
