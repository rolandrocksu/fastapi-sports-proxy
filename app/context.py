# Moved to app/lib/context.py — this re-export keeps imports working.
from app.lib.context import request_id_var  # noqa: F401

__all__ = ["request_id_var"]
