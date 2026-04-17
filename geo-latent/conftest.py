"""
conftest.py
Pytest fixtures — provides a mock lifespan so tests run without Postgres/Redis.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Async event loop
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Mock database pool
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_pool():
    """Returns a mock AsyncConnectionPool whose .connection() yields a mock conn."""
    pool = MagicMock()
    conn = AsyncMock()

    # fetchone → returns None by default
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=None)
    cursor.fetchall = AsyncMock(return_value=[])
    conn.execute = AsyncMock(return_value=cursor)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__  = AsyncMock(return_value=False)
    pool.connection = MagicMock(return_value=cm)
    pool.open  = AsyncMock()
    pool.close = AsyncMock()
    return pool


# ---------------------------------------------------------------------------
# Mock engine
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.current_frame  = MagicMock(return_value={"step": 1, "sea_level": 0.15, "active": 10, "total_energy": 8.5})
    engine.current_scene  = MagicMock(return_value={"vertices": [], "faces": [], "biomes": {}, "entities": []})
    engine.current_report = MagicMock(return_value={"stability_index": 0.82, "drift": 0.1})
    engine.get_controls   = MagicMock(return_value={"variance": 1.0, "temperature": 1.0})
    engine.set_controls   = MagicMock()
    engine.set_observer   = MagicMock()
    engine.pause          = MagicMock()
    engine.resume         = MagicMock()
    engine.step_once      = MagicMock()
    engine.run_once       = MagicMock()
    engine.snapshot       = MagicMock(return_value={"step": 1})
    return engine


# ---------------------------------------------------------------------------
# TestClient with mocked lifespan
# ---------------------------------------------------------------------------

@pytest.fixture
def client(mock_pool, mock_engine, monkeypatch):
    """
    HTTPX AsyncClient with the full app but mocked lifespan.
    No real Postgres or Redis required.
    """
    @asynccontextmanager
    async def mock_lifespan(app):
        app.state.db_pool          = mock_pool
        app.state.redis            = None
        app.state.engine           = mock_engine
        app.state.ws_clients       = set()
        app.state.observer_registry = {}
        yield

    try:
        from geolatent import api as _api
        monkeypatch.setattr(_api, "lifespan", mock_lifespan)
        from geolatent.api import app
        app.router.lifespan_context = mock_lifespan

        from httpx import AsyncClient, ASGITransport
        import pytest_asyncio
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Environment defaults for tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def test_env(monkeypatch):
    monkeypatch.setenv("GEOLATENT_JWT_SECRET",        "test-secret-do-not-use")
    monkeypatch.setenv("GEOLATENT_AUDIT_SIGNING_KEY", "test-audit-key")
    monkeypatch.setenv("GEOLATENT_BUNDLE_SECRET",     "test-bundle-key")
    monkeypatch.setenv("GEOLATENT_ALLOW_HEADER_DEV",  "true")
