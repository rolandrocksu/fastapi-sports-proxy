import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.middleware import RequestResponseMiddleware
from app.router import router


def _configure_logging() -> None:
    """Route app loggers to stdout with a plain-message format (JSON lines)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))

    for name in ("app.audit", "app.middleware"):
        lg = logging.getLogger(name)
        if not lg.handlers:
            lg.addHandler(handler)
        lg.setLevel(logging.INFO)
        lg.propagate = True  # allow pytest caplog to capture records


_configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.provider == "openliga":
        from app.providers.openliga import OpenLigaAdapter
        from app.api_clients.openliga_client import OpenLigaClient
        from app.rate_limiter import RateLimiter

        client = OpenLigaClient(RateLimiter(rps=settings.rate_limit_rps))
        app.state.provider = OpenLigaAdapter(client)
        app.state.provider_name = "openliga"
    else:
        raise RuntimeError(f"Unknown provider: {settings.provider}")

    yield

    if hasattr(app.state, "provider") and hasattr(app.state.provider, "close"):
        await app.state.provider.close()


app = FastAPI(title="Generic Reverse Proxy", lifespan=lifespan)
app.add_middleware(RequestResponseMiddleware)
app.include_router(router)
