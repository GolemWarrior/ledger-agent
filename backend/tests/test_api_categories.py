"""Tests for api/categories.py — GET/POST/PATCH/DELETE /api/v1/categories endpoints."""
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from ledger_agent.api.categories import categories_router


def _make_cat(cat_id, name, hint=None):
    cat = MagicMock()
    cat.id = cat_id
    cat.name = name
    cat.hint = hint
    return cat


def _make_app(scalar_return=None, scalars_rows=None, execute_side_effect=None):
    """Build a test FastAPI app with a mocked async session."""
    app = FastAPI()
    app.include_router(categories_router, prefix="/api/v1")

    session = AsyncMock()

    if scalars_rows is not None:
        session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=scalars_rows)))
    elif execute_side_effect is not None:
        session.execute = AsyncMock(side_effect=execute_side_effect)
    else:
        session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    session.scalar = AsyncMock(return_value=scalar_return)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()

    class _Ctx:
        async def __aenter__(self): return session
        async def __aexit__(self, *_): pass

    app.state.async_session_factory = lambda: _Ctx()
    return TestClient(app), session


# ── GET /api/v1/categories ──────────────────────────────────────────────────

def test_list_categories_empty():
    client, _ = _make_app(scalars_rows=[])
    resp = client.get("/api/v1/categories")
    assert resp.status_code == 200
    assert resp.json() == {"data": [], "total": 0}


def test_list_categories_returns_envelope():
    cat = _make_cat(1, "Food", "groceries and dining")
    rows = [(cat, 5)]
    client, _ = _make_app(scalars_rows=rows)
    resp = client.get("/api/v1/categories")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "total" in body
    assert body["total"] == 1


def test_list_categories_shape():
    cat = _make_cat(1, "Food", "groceries and dining")
    rows = [(cat, 5)]
    client, _ = _make_app(scalars_rows=rows)
    resp = client.get("/api/v1/categories")
    item = resp.json()["data"][0]
    assert item["id"] == 1
    assert item["name"] == "Food"
    assert item["hint"] == "groceries and dining"
    assert item["transaction_count"] == 5


def test_list_categories_null_hint():
    cat = _make_cat(2, "Misc", None)
    rows = [(cat, 0)]
    client, _ = _make_app(scalars_rows=rows)
    resp = client.get("/api/v1/categories")
    item = resp.json()["data"][0]
    assert item["hint"] is None
    assert item["transaction_count"] == 0


# ── POST /api/v1/categories ─────────────────────────────────────────────────

def test_create_category_success():
    new_cat = _make_cat(10, "Side Project", "software tools for freelance")
    new_cat.id = 10

    def _refresh_side_effect(obj):
        obj.id = 10
        obj.name = "Side Project"
        obj.hint = "software tools for freelance"

    client, session = _make_app()
    session.refresh = AsyncMock(side_effect=_refresh_side_effect)

    resp = client.post("/api/v1/categories", json={"name": "Side Project", "hint": "software tools for freelance"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["transaction_count"] == 0
    assert body["data"]["name"] == "Side Project"


def test_create_category_empty_name_returns_400():
    client, _ = _make_app()
    resp = client.post("/api/v1/categories", json={"name": "", "hint": None})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "bad_input"


def test_create_category_missing_name_returns_400():
    client, _ = _make_app()
    resp = client.post("/api/v1/categories", json={"hint": "something"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "bad_input"


def test_create_category_duplicate_name_returns_409():
    client, session = _make_app()
    session.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))
    resp = client.post("/api/v1/categories", json={"name": "Food"})
    assert resp.status_code == 409
    assert resp.json()["error"] == "duplicate_name"


def test_create_category_no_hint():
    def _refresh(obj):
        obj.id = 5
        obj.name = "No Hint Cat"
        obj.hint = None

    client, session = _make_app()
    session.refresh = AsyncMock(side_effect=_refresh)
    resp = client.post("/api/v1/categories", json={"name": "No Hint Cat"})
    assert resp.status_code == 201
    assert resp.json()["data"]["hint"] is None


# ── PATCH /api/v1/categories/{id} ───────────────────────────────────────────

def test_rename_category_success():
    cat = _make_cat(1, "Food", "groceries")
    client, session = _make_app(scalar_return=cat)
    resp = client.patch("/api/v1/categories/1", json={"name": "Groceries"})
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert body["data"]["name"] == "Groceries"


def test_rename_category_not_found():
    client, session = _make_app(scalar_return=None)
    resp = client.patch("/api/v1/categories/999", json={"name": "New Name"})
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_rename_category_empty_name_returns_400():
    client, _ = _make_app()
    resp = client.patch("/api/v1/categories/1", json={"name": ""})
    assert resp.status_code == 400
    assert resp.json()["error"] == "bad_input"


def test_rename_uncategorized_returns_400():
    cat = _make_cat(1, "Uncategorized", None)
    client, session = _make_app(scalar_return=cat)
    resp = client.patch("/api/v1/categories/1", json={"name": "Something Else"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "cannot_rename_uncategorized"


def test_rename_category_duplicate_name_returns_409():
    cat = _make_cat(1, "Food", "groceries")
    client, session = _make_app(scalar_return=cat)
    session.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))
    resp = client.patch("/api/v1/categories/1", json={"name": "Shopping"})
    assert resp.status_code == 409
    assert resp.json()["error"] == "duplicate_name"


# ── DELETE /api/v1/categories/{id} ──────────────────────────────────────────

def test_delete_category_not_found():
    client, session = _make_app(scalar_return=None)
    resp = client.delete("/api/v1/categories/999")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_delete_uncategorized_returns_400():
    cat = _make_cat(1, "Uncategorized", None)
    client, session = _make_app(scalar_return=cat)
    resp = client.delete("/api/v1/categories/1")
    assert resp.status_code == 400
    assert resp.json()["error"] == "cannot_delete_uncategorized"


def test_delete_category_success():
    cat_to_delete = _make_cat(5, "Shopping", None)
    uncategorized = _make_cat(1, "Uncategorized", None)

    call_count = [0]

    async def _scalar(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return cat_to_delete
        return uncategorized

    client, session = _make_app()
    session.scalar = AsyncMock(side_effect=_scalar)

    resp = client.delete("/api/v1/categories/5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["deleted"] is True
    session.delete.assert_called_once_with(cat_to_delete)
    session.commit.assert_called_once()
    assert session.execute.call_count == 2  # Transaction bulk update + VendorMemory bulk update
