import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.providers.base import SportsProvider


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_provider():
    """An AsyncMock that satisfies the SportsProvider interface."""
    provider = AsyncMock(spec=SportsProvider)
    return provider


@pytest.fixture
def client(mock_provider):
    """
    TestClient with the real lifespan (creates real OpenLigaProvider),
    then immediately replaces app.state.provider with the mock so no
    real HTTP calls are made during tests.
    """
    with TestClient(app) as c:
        app.state.provider = mock_provider
        app.state.provider_name = "mock"
        yield c, mock_provider
