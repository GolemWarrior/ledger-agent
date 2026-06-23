"""Tests for api/sync.py — POST /sync and GET /sync/status endpoints."""
import threading
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ledger_agent.api.sync import sync_router
from ledger_agent.db.models import SyncRunStatus



def _make_full_app(active_sync=False, latest_run=None, last_synced_at=None, account_exists=True):
    """Build a FastAPI test app with fully mocked app.state."""
    from fastapi import FastAPI
    from ledger_agent.api.sync import sync_router

    app = FastAPI()
    app.include_router(sync_router, prefix="/api/v1")

    mock_sync_run = MagicMock()
    mock_sync_run.id = 42

    async def scalar_for_post(stmt):
        # POST /sync: first scalar is active check
        return MagicMock() if active_sync else None

    async def scalar_for_get_1(stmt):
        return latest_run

    async def scalar_for_get_2(stmt):
        return last_synced_at

    post_session = AsyncMock()
    post_session.scalar = AsyncMock(return_value=MagicMock() if active_sync else None)
    post_session.add = MagicMock()
    post_session.commit = AsyncMock()
    post_session.refresh = AsyncMock()

    get_call_count = {"n": 0}
    get_session = AsyncMock()

    async def get_scalar(stmt):
        get_call_count["n"] += 1
        if get_call_count["n"] == 1:
            return latest_run
        return last_synced_at

    get_session.scalar = AsyncMock(side_effect=get_scalar)

    class _Ctx:
        def __init__(self, session):
            self._session = session

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, *_):
            pass

    def factory():
        return _Ctx(post_session)

    def get_factory():
        return _Ctx(get_session)

    # Use a single factory that alternates based on call count
    factory_call_count = {"n": 0}

    def combined_factory():
        factory_call_count["n"] += 1
        if factory_call_count["n"] == 1:
            post_session.refresh.side_effect = lambda sr: setattr(sr, "id", 42)
            return _Ctx(post_session)
        return _Ctx(get_session)

    app.state.async_session_factory = combined_factory
    app.state.sync_session_factory = MagicMock()
    app.state.plaid_client = MagicMock()

    return app, post_session, get_session


@pytest.fixture
def client_no_active():
    app, post_session, get_session = _make_full_app(active_sync=False)
    return TestClient(app), post_session, get_session


@pytest.fixture
def client_active():
    app, post_session, _ = _make_full_app(active_sync=True)
    return TestClient(app)


def test_post_sync_returns_202_with_sync_run_id():
    """POST /sync creates a SyncRun and returns 202 with sync_run_id."""
    app, post_session, _ = _make_full_app(active_sync=False)
    with patch("ledger_agent.api.sync.threading.Thread") as mock_thread:
        mock_thread.return_value = MagicMock()
        client = TestClient(app)
        resp = client.post("/api/v1/sync")

    assert resp.status_code == 202
    data = resp.json()
    assert "data" in data
    assert "sync_run_id" in data["data"]


def test_post_sync_returns_409_when_active():
    """POST /sync returns 409 if a sync is already in progress."""
    app, _, _ = _make_full_app(active_sync=True)
    client = TestClient(app)
    resp = client.post("/api/v1/sync")
    assert resp.status_code == 409


def test_post_sync_spawns_background_thread():
    """POST /sync spawns exactly one daemon thread."""
    app, _, _ = _make_full_app(active_sync=False)
    with patch("ledger_agent.api.sync.threading.Thread") as mock_thread:
        instance = MagicMock()
        mock_thread.return_value = instance
        client = TestClient(app)
        client.post("/api/v1/sync")

    mock_thread.assert_called_once()
    kwargs = mock_thread.call_args.kwargs
    assert kwargs.get("daemon") is True
    instance.start.assert_called_once()


def test_get_sync_status_idle_when_no_runs():
    """GET /sync/status returns idle with zeros when no SyncRun exists."""
    app, _, _ = _make_full_app(active_sync=False, latest_run=None)

    get_call_count = {"n": 0}
    get_session = AsyncMock()

    async def get_scalar(stmt):
        get_call_count["n"] += 1
        return None

    get_session.scalar = AsyncMock(side_effect=get_scalar)

    class _Ctx:
        async def __aenter__(self):
            return get_session
        async def __aexit__(self, *_):
            pass

    app.state.async_session_factory = lambda: _Ctx()
    client = TestClient(app)
    resp = client.get("/api/v1/sync/status")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "idle"
    assert data["processed"] == 0
    assert data["total"] == 0
    assert data["last_synced_at"] is None
    assert data["error"] is None


def test_get_sync_status_returns_latest_run():
    """GET /sync/status returns status from latest SyncRun."""
    mock_run = MagicMock()
    mock_run.status = SyncRunStatus.complete
    mock_run.processed = 10
    mock_run.total = 10
    mock_run.error = None

    last_synced = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
    get_call_count = {"n": 0}
    get_session = AsyncMock()

    async def get_scalar(stmt):
        get_call_count["n"] += 1
        if get_call_count["n"] == 1:
            return mock_run
        return last_synced

    get_session.scalar = AsyncMock(side_effect=get_scalar)

    class _Ctx:
        async def __aenter__(self):
            return get_session
        async def __aexit__(self, *_):
            pass

    app = FastAPI()
    app.include_router(sync_router, prefix="/api/v1")
    app.state.async_session_factory = lambda: _Ctx()
    app.state.sync_session_factory = MagicMock()
    app.state.plaid_client = MagicMock()

    client = TestClient(app)
    resp = client.get("/api/v1/sync/status")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "complete"
    assert data["processed"] == 10
    assert data["total"] == 10
    assert data["last_synced_at"] == last_synced.isoformat()
    assert data["error"] is None
