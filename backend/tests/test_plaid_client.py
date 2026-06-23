"""Tests for ingestion/plaid_client.py — fetch_transactions."""
from datetime import date
from unittest.mock import MagicMock

import pytest

from ledger_agent.ingestion.plaid_client import fetch_transactions


def _make_txn(txn_id: str, name: str, amount: float, merchant: str | None = None):
    return {
        "transaction_id": txn_id,
        "name": name,
        "amount": amount,
        "date": date(2026, 1, 1),
        "merchant_name": merchant,
    }


def test_fetch_transactions_single_page():
    """Fetches all transactions when total fits in one page."""
    client = MagicMock()
    txns = [_make_txn("t1", "Starbucks", 5.50, "Starbucks"), _make_txn("t2", "Amazon", 99.0)]
    client.transactions_get.return_value = {
        "transactions": txns,
        "total_transactions": 2,
    }

    result = fetch_transactions(client, "access-sandbox-xxx", date(2026, 1, 1), date(2026, 1, 31))

    assert len(result) == 2
    assert result[0]["plaid_transaction_id"] == "t1"
    assert result[0]["description"] == "Starbucks"
    assert result[0]["amount"] == 5.50
    assert result[0]["merchant_name"] == "Starbucks"
    assert result[0]["date"] == date(2026, 1, 1)
    assert result[1]["merchant_name"] is None
    client.transactions_get.assert_called_once()


def test_fetch_transactions_pagination():
    """Paginates when total_transactions > page size."""
    client = MagicMock()
    page1 = [_make_txn(f"t{i}", f"Merchant {i}", float(i)) for i in range(3)]
    page2 = [_make_txn(f"t{i+3}", f"Merchant {i+3}", float(i+3)) for i in range(2)]

    client.transactions_get.side_effect = [
        {"transactions": page1, "total_transactions": 5},
        {"transactions": page2, "total_transactions": 5},
    ]

    result = fetch_transactions(client, "access-sandbox-xxx", date(2026, 1, 1), date(2026, 1, 31))

    assert len(result) == 5
    assert client.transactions_get.call_count == 2


def test_fetch_transactions_empty():
    """Returns empty list when Plaid returns 0 transactions."""
    client = MagicMock()
    client.transactions_get.return_value = {"transactions": [], "total_transactions": 0}

    result = fetch_transactions(client, "access-sandbox-xxx", date(2026, 1, 1), date(2026, 1, 31))

    assert result == []
    client.transactions_get.assert_called_once()


def test_fetch_transactions_uses_transaction_id_not_id():
    """Ensures plaid_transaction_id maps from txn['transaction_id'], not txn['id']."""
    client = MagicMock()
    txn = {"transaction_id": "plaid-tid-abc", "name": "Coffee", "amount": 3.0, "date": date(2026, 1, 5), "merchant_name": None}
    txn["id"] = "wrong-field"
    client.transactions_get.return_value = {"transactions": [txn], "total_transactions": 1}

    result = fetch_transactions(client, "access-sandbox-xxx", date(2026, 1, 1), date(2026, 1, 31))

    assert result[0]["plaid_transaction_id"] == "plaid-tid-abc"
