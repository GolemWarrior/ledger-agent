"""Tests for api/vendor_memory.py — GET/PATCH/DELETE /api/v1/vendor-memory endpoints."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ledger_agent.api.vendor_memory import vendor_memory_router

_DT = datetime(2026, 6, 20, 14, 32, 0, tzinfo=timezone.utc)


def _make_vm(vm_id, vendor, category_id, category_name, hit_count=3, last_used_at=None):
    vm = MagicMock()
    vm.id = vm_id
    vm.vendor = vendor
    vm.category_id = category_id
    vm.hit_count = hit_count
    vm.last_used_at = last_used_at or _DT
    vm.category = MagicMock()
    vm.category.name = category_name
    return vm


def _make_cat(cat_id, name):
    cat = MagicMock()
    cat.id = cat_id
    cat.name = name
    return cat


def _make_app(scalar_return=None, scalars_rows=None):
    """Build a test FastAPI app with a mocked async session."""
    app = FastAPI()
    app.include_router(vendor_memory_router, prefix="/api/v1")

    session = AsyncMock()

    result_mock = MagicMock()
    result_mock.all.return_value = scalars_rows if scalars_rows is not None else []
    session.scalars = AsyncMock(return_value=result_mock)

    session.scalar = AsyncMock(return_value=scalar_return)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()

    class _Ctx:
        async def __aenter__(self): return session
        async def __aexit__(self, *_): pass

    app.state.async_session_factory = lambda: _Ctx()
    return TestClient(app), session


# ── GET /api/v1/vendor-memory ───────────────────────────────────────────────

def test_list_vendor_memory_empty():
    client, _ = _make_app(scalars_rows=[])
    resp = client.get("/api/v1/vendor-memory")
    assert resp.status_code == 200
    assert resp.json() == {"data": [], "total": 0}


def test_list_vendor_memory_returns_envelope():
    vm = _make_vm(1, "Amazon", 2, "Electronics")
    client, _ = _make_app(scalars_rows=[vm])
    resp = client.get("/api/v1/vendor-memory")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "total" in body
    assert body["total"] == 1


def test_list_vendor_memory_shape():
    vm = _make_vm(1, "Amazon", 2, "Electronics", hit_count=5)
    client, _ = _make_app(scalars_rows=[vm])
    resp = client.get("/api/v1/vendor-memory")
    item = resp.json()["data"][0]
    assert item["id"] == 1
    assert item["vendor"] == "Amazon"
    assert item["category_id"] == 2
    assert item["category_name"] == "Electronics"
    assert item["hit_count"] == 5
    assert item["last_used_at"] == _DT.isoformat()


def test_list_vendor_memory_multiple_entries():
    vms = [
        _make_vm(1, "Amazon", 2, "Electronics"),
        _make_vm(2, "Trader Joe's", 3, "Groceries"),
    ]
    client, _ = _make_app(scalars_rows=vms)
    resp = client.get("/api/v1/vendor-memory")
    assert resp.json()["total"] == 2
    assert len(resp.json()["data"]) == 2


# ── PATCH /api/v1/vendor-memory/{id} ────────────────────────────────────────

def test_reassign_category_success():
    vm = _make_vm(1, "Amazon", 2, "Electronics")
    cat = _make_cat(3, "Household")

    client, session = _make_app()
    session.scalar = AsyncMock(side_effect=[vm, cat])

    resp = client.patch("/api/v1/vendor-memory/1", json={"category_id": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert body["data"]["category_name"] == "Household"
    assert body["data"]["category_id"] == 3
    session.commit.assert_called_once()


def test_reassign_category_not_found():
    client, session = _make_app(scalar_return=None)
    resp = client.patch("/api/v1/vendor-memory/999", json={"category_id": 1})
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_reassign_category_invalid_category():
    vm = _make_vm(1, "Amazon", 2, "Electronics")

    client, session = _make_app()
    session.scalar = AsyncMock(side_effect=[vm, None])

    resp = client.patch("/api/v1/vendor-memory/1", json={"category_id": 999})
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_reassign_category_missing_body_field():
    client, _ = _make_app()
    resp = client.patch("/api/v1/vendor-memory/1", json={})
    assert resp.status_code == 400
    assert resp.json()["error"] == "bad_input"


# ── DELETE /api/v1/vendor-memory/{id} ───────────────────────────────────────

def test_delete_vendor_memory_success():
    vm = _make_vm(1, "Amazon", 2, "Electronics")
    client, session = _make_app(scalar_return=vm)
    resp = client.delete("/api/v1/vendor-memory/1")
    assert resp.status_code == 200
    assert resp.json() == {"data": {"deleted": True}}
    session.delete.assert_called_once_with(vm)
    session.commit.assert_called_once()


def test_delete_vendor_memory_not_found():
    client, session = _make_app(scalar_return=None)
    resp = client.delete("/api/v1/vendor-memory/999")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"
