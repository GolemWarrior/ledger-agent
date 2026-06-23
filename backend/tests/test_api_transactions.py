"""Tests for api/transactions.py — GET /api/v1/transactions endpoint."""
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ledger_agent.api.transactions import transactions_router
from ledger_agent.db.models import TransactionStatus


def _make_txn(txn_id, description, amount, txn_date, status, account_name, category_name=None, confidence=None, reasoning_trace=None, escalation_question=None):
    txn = MagicMock()
    txn.id = txn_id
    txn.description = description
    txn.merchant_name = None
    txn.amount = Decimal(amount) if isinstance(amount, str) else Decimal(f"{amount:.2f}")
    txn.date = txn_date
    txn.status = status
    txn.account = MagicMock()
    txn.account.name = account_name
    txn.category = MagicMock() if category_name else None
    if category_name:
        txn.category.name = category_name
    txn.confidence_score = confidence
    txn.reasoning_trace = reasoning_trace
    txn.escalation_question = escalation_question
    return txn


def _make_app(transactions: list):
    app = FastAPI()
    app.include_router(transactions_router, prefix="/api/v1")

    session = AsyncMock()
    session.scalars = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=transactions)))

    class _Ctx:
        async def __aenter__(self): return session
        async def __aexit__(self, *_): pass

    app.state.async_session_factory = lambda: _Ctx()
    return TestClient(app)


def _make_app_detail(txn_or_none):
    app = FastAPI()
    app.include_router(transactions_router, prefix="/api/v1")
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=txn_or_none)

    class _Ctx:
        async def __aenter__(self): return session
        async def __aexit__(self, *_): pass

    app.state.async_session_factory = lambda: _Ctx()
    return TestClient(app)


def test_list_transactions_empty():
    client = _make_app([])
    resp = client.get("/api/v1/transactions")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"data": [], "total": 0}


def test_list_transactions_returns_all():
    txns = [
        _make_txn(1, "Amazon", 42.00, date(2026, 1, 10), TransactionStatus.resolved, "Checking", "Shopping", 0.95),
        _make_txn(2, "Starbucks", 5.50, date(2026, 1, 9), TransactionStatus.pending, "Savings"),
    ]
    client = _make_app(txns)
    resp = client.get("/api/v1/transactions")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert resp.json()["total"] == 2


def test_list_transactions_shape():
    txn = _make_txn(1, "Amazon", 42.00, date(2026, 1, 10), TransactionStatus.resolved, "Checking", "Shopping", 0.95)
    client = _make_app([txn])
    resp = client.get("/api/v1/transactions")
    row = resp.json()["data"][0]
    assert row["id"] == 1
    assert row["description"] == "Amazon"
    assert row["amount"] == "42.00"
    assert row["date"] == "2026-01-10"
    assert row["status"] == "resolved"
    assert row["account_name"] == "Checking"
    assert row["category_name"] == "Shopping"
    assert row["confidence_score"] == 0.95


def test_list_transactions_no_category():
    txn = _make_txn(2, "Starbucks", 5.50, date(2026, 1, 9), TransactionStatus.pending, "Savings")
    client = _make_app([txn])
    resp = client.get("/api/v1/transactions")
    row = resp.json()["data"][0]
    assert row["category_name"] is None
    assert row["confidence_score"] is None


def test_list_transactions_transfer_status():
    txn = _make_txn(3, "Transfer to Savings", 200.00, date(2026, 1, 8), TransactionStatus.transfer, "Checking", "Transfer")
    client = _make_app([txn])
    resp = client.get("/api/v1/transactions")
    row = resp.json()["data"][0]
    assert row["status"] == "transfer"
    assert row["category_name"] == "Transfer"


def test_list_transactions_transfer_no_category_defaults_to_transfer_label():
    txn = _make_txn(4, "Transfer to Savings", 200.00, date(2026, 1, 8), TransactionStatus.transfer, "Checking")
    client = _make_app([txn])
    resp = client.get("/api/v1/transactions")
    row = resp.json()["data"][0]
    assert row["status"] == "transfer"
    assert row["category_name"] == "Transfer"


def test_get_transaction_detail_resolved():
    txn = _make_txn(
        1, "Amazon", 42.00, date(2026, 1, 10), TransactionStatus.resolved,
        "Checking", "Shopping", 0.95,
        reasoning_trace="Vendor memory matched Amazon → Shopping (confidence 0.95)",
    )
    client = _make_app_detail(txn)
    resp = client.get("/api/v1/transactions/1")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert body["data"]["reasoning_trace"] == "Vendor memory matched Amazon → Shopping (confidence 0.95)"
    assert body["data"]["escalation_question"] is None


def test_get_transaction_detail_escalated():
    txn = _make_txn(
        2, "Some Purchase", 15.00, date(2026, 1, 11), TransactionStatus.escalated,
        "Savings", escalation_question="Is this a groceries or dining expense?",
    )
    client = _make_app_detail(txn)
    resp = client.get("/api/v1/transactions/2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["escalation_question"] == "Is this a groceries or dining expense?"
    assert body["data"]["reasoning_trace"] is None


def test_get_transaction_detail_not_found():
    client = _make_app_detail(None)
    resp = client.get("/api/v1/transactions/999")
    assert resp.status_code == 404
    body = resp.json()
    assert body == {"error": "not_found", "detail": "Transaction not found"}


def test_get_transaction_detail_resolved_has_no_escalation_question():
    txn = _make_txn(
        6, "Amazon", 42.00, date(2026, 1, 10), TransactionStatus.resolved,
        "Checking", "Shopping", 0.95,
        reasoning_trace="Matched Amazon → Shopping",
    )
    client = _make_app_detail(txn)
    resp = client.get("/api/v1/transactions/6")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["reasoning_trace"] is not None
    assert data["escalation_question"] is None


def test_get_transaction_detail_escalated_has_no_reasoning_trace():
    txn = _make_txn(
        7, "Some Purchase", 15.00, date(2026, 1, 11), TransactionStatus.escalated,
        "Savings", escalation_question="Is this groceries or dining?",
    )
    client = _make_app_detail(txn)
    resp = client.get("/api/v1/transactions/7")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["escalation_question"] is not None
    assert data["reasoning_trace"] is None


def test_get_transaction_detail_includes_all_fields():
    txn = _make_txn(
        5, "Starbucks", 5.50, date(2026, 2, 1), TransactionStatus.resolved,
        "Checking", "Dining", 0.88,
        reasoning_trace="Matched Starbucks → Dining",
    )
    txn.merchant_name = "Starbucks"
    client = _make_app_detail(txn)
    resp = client.get("/api/v1/transactions/5")
    assert resp.status_code == 200
    data = resp.json()["data"]
    for field in ("id", "description", "merchant_name", "amount", "date", "status",
                  "account_name", "category_name", "confidence_score",
                  "reasoning_trace", "escalation_question"):
        assert field in data, f"Missing field: {field}"
