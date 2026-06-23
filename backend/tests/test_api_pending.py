"""Tests for api/pending.py — GET /api/v1/transactions/pending endpoint."""
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ledger_agent.api.pending import pending_router
from ledger_agent.db.models import TransactionStatus


def _make_txn(txn_id=1, question="Is this business or personal?"):
    txn = MagicMock()
    txn.id = txn_id
    txn.description = "UBER EATS"
    txn.merchant_name = "Uber Eats"
    txn.amount = Decimal("28.50")
    txn.date = date(2026, 6, 10)
    txn.status = TransactionStatus.escalated
    txn.category = None
    txn.account = MagicMock()
    txn.account.name = "Checking"
    txn.escalation_question = question
    return txn


def _make_app(transactions: list):
    app = FastAPI()
    app.include_router(pending_router, prefix="/api/v1")

    session = AsyncMock()
    session.scalars = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=transactions)))

    class _Ctx:
        async def __aenter__(self): return session
        async def __aexit__(self, *_): pass

    app.state.async_session_factory = lambda: _Ctx()
    return TestClient(app)


def test_list_pending_returns_escalated_transactions():
    txn = _make_txn()
    client = _make_app([txn])
    response = client.get("/api/v1/transactions/pending")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["data"][0]["escalation_question"] == "Is this business or personal?"
    assert body["data"][0]["description"] == "UBER EATS"
    assert body["data"][0]["account_name"] == "Checking"
    assert body["data"][0]["category_name"] is None
    assert body["data"][0]["amount"] == "28.50"
    assert body["data"][0]["date"] == "2026-06-10"


def test_list_pending_empty_when_no_escalations():
    client = _make_app([])
    response = client.get("/api/v1/transactions/pending")

    assert response.status_code == 200
    assert response.json() == {"data": [], "total": 0}


def test_list_pending_shape():
    txn = _make_txn(txn_id=42, question="Is this dining or entertainment?")
    client = _make_app([txn])
    response = client.get("/api/v1/transactions/pending")

    row = response.json()["data"][0]
    assert row["id"] == 42
    assert row["merchant_name"] == "Uber Eats"
    assert row["escalation_question"] == "Is this dining or entertainment?"
