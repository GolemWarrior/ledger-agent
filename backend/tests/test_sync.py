"""Tests for ingestion/sync.py — run_full_sync and detect_transfers."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

from ledger_agent.db.models import SyncRunStatus, TransactionStatus
from ledger_agent.ingestion.sync import detect_transfers, run_full_sync


def _make_account(account_id=1, access_token="access-tok", last_synced_at=None):
    account = MagicMock()
    account.id = account_id
    account.access_token = access_token
    account.last_synced_at = last_synced_at
    return account


def _make_sync_run(sync_run_id=1):
    sync_run = MagicMock()
    sync_run.id = sync_run_id
    sync_run.status = SyncRunStatus.processing
    sync_run.processed = 0
    sync_run.total = 0
    return sync_run


def _make_session(accounts, sync_run, existing_txn_ids=None):
    """Build a mock session that returns given accounts and sync_run."""
    session = MagicMock()
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)

    session.get.return_value = sync_run
    session.scalars.return_value = iter(accounts)

    existing_txn_ids = existing_txn_ids or set()

    def scalar_side_effect(stmt):
        # Called for duplicate check: returns None (new) or a mock (duplicate)
        # We inspect the statement's whereclause for the transaction id
        return MagicMock() if _extract_txn_id(stmt) in existing_txn_ids else None

    session.scalar.side_effect = scalar_side_effect
    return session


def _extract_txn_id(stmt):
    """Crude: pull the plaid_transaction_id from whereclause string for test assertions."""
    where_str = str(stmt)
    # The whereclause contains "= :plaid_transaction_id_1" — we check via the bound params
    try:
        return stmt.whereclause.right.value
    except Exception:
        return None


def _make_factory(session):
    factory = MagicMock()
    factory.return_value.__enter__ = lambda s: session
    factory.return_value.__exit__ = MagicMock(return_value=False)
    return factory


def test_run_full_sync_writes_new_transactions():
    """New transactions get written to DB; sync_run stays processing (agent marks complete)."""
    sync_run = _make_sync_run()
    account = _make_account()
    session = _make_session([account], sync_run)
    factory = _make_factory(session)

    plaid_txns = [
        {"plaid_transaction_id": "t1", "description": "Coffee", "merchant_name": "Starbucks", "amount": 5.0, "date": date(2026, 1, 1)},
        {"plaid_transaction_id": "t2", "description": "Groceries", "merchant_name": None, "amount": 50.0, "date": date(2026, 1, 2)},
    ]
    plaid_client = MagicMock()

    with patch("ledger_agent.ingestion.sync.fetch_transactions", return_value=plaid_txns) as mock_fetch:
        run_full_sync(factory, plaid_client, sync_run_id=1)

    assert session.add.call_count == 2
    assert sync_run.processed == 2
    assert sync_run.total == 2
    # sync_run stays processing — run_classification_agent marks it complete
    assert sync_run.status == SyncRunStatus.processing


def test_run_full_sync_skips_duplicates():
    """Transactions with existing plaid_transaction_id are silently skipped."""
    sync_run = _make_sync_run()
    account = _make_account()

    # "t1" already exists; "t2" is new
    session = _make_session([account], sync_run, existing_txn_ids={"t1"})
    factory = _make_factory(session)

    plaid_txns = [
        {"plaid_transaction_id": "t1", "description": "Dup", "merchant_name": None, "amount": 10.0, "date": date(2026, 1, 1)},
        {"plaid_transaction_id": "t2", "description": "New", "merchant_name": None, "amount": 20.0, "date": date(2026, 1, 2)},
    ]

    with patch("ledger_agent.ingestion.sync.fetch_transactions", return_value=plaid_txns):
        run_full_sync(factory, plaid_client=MagicMock(), sync_run_id=1)

    assert session.add.call_count == 1
    assert sync_run.processed == 1
    assert sync_run.total == 2


def test_run_full_sync_uses_last_synced_at_as_start_date():
    """If account.last_synced_at is set, it's used as start_date."""
    sync_run = _make_sync_run()
    last_synced = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
    account = _make_account(last_synced_at=last_synced)
    session = _make_session([account], sync_run)
    factory = _make_factory(session)

    with patch("ledger_agent.ingestion.sync.fetch_transactions", return_value=[]) as mock_fetch:
        run_full_sync(factory, plaid_client=MagicMock(), sync_run_id=1)

    args = mock_fetch.call_args
    assert args[0][2] == last_synced.date()  # start_date


def test_run_full_sync_uses_90_days_back_when_no_last_synced():
    """First sync uses today - 90 days as start_date."""
    sync_run = _make_sync_run()
    account = _make_account(last_synced_at=None)
    session = _make_session([account], sync_run)
    factory = _make_factory(session)

    with patch("ledger_agent.ingestion.sync.fetch_transactions", return_value=[]) as mock_fetch:
        with patch("ledger_agent.ingestion.sync.date") as mock_date:
            mock_date.today.return_value = date(2026, 6, 21)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            run_full_sync(factory, plaid_client=MagicMock(), sync_run_id=1)

    args = mock_fetch.call_args
    assert args[0][2] == date(2026, 3, 23)  # 90 days before 2026-06-21


def test_run_full_sync_error_path_writes_to_db():
    """If fetch_transactions raises, sync_run.status is set to error and finished_at is set."""
    sync_run = _make_sync_run()
    account = _make_account()
    session = _make_session([account], sync_run)
    factory = _make_factory(session)

    with patch("ledger_agent.ingestion.sync.fetch_transactions", side_effect=RuntimeError("plaid down")):
        run_full_sync(factory, plaid_client=MagicMock(), sync_run_id=1)

    assert sync_run.status == SyncRunStatus.error
    assert "plaid down" in sync_run.error
    assert sync_run.finished_at is not None
    # Must not propagate — function returns normally


def test_run_full_sync_sets_transaction_status_pending():
    """All new transactions get status = TransactionStatus.pending regardless of Plaid pending field."""
    sync_run = _make_sync_run()
    account = _make_account()
    session = _make_session([account], sync_run)
    factory = _make_factory(session)

    plaid_txns = [{"plaid_transaction_id": "t1", "description": "Buy", "merchant_name": None, "amount": 10.0, "date": date(2026, 1, 1)}]

    with patch("ledger_agent.ingestion.sync.fetch_transactions", return_value=plaid_txns):
        run_full_sync(factory, plaid_client=MagicMock(), sync_run_id=1)

    added_txn = session.add.call_args[0][0]
    assert added_txn.status == TransactionStatus.pending


# ── detect_transfers tests ────────────────────────────────────────────────────


def _make_txn(txn_id, account_id, amount, txn_date, status=TransactionStatus.pending):
    txn = MagicMock()
    txn.id = txn_id
    txn.account_id = account_id
    txn.amount = Decimal(str(amount))
    txn.date = txn_date
    txn.status = status
    txn.category_id = None
    txn.transfer_counterpart_id = None
    return txn


def _make_category(cat_id=10, name="Transfer"):
    cat = MagicMock()
    cat.id = cat_id
    cat.name = name
    return cat


def test_detect_transfers_tags_matching_pair():
    """Same amount (opposite signs), different accounts, same date → both tagged transfer."""
    txn_a = _make_txn(1, account_id=1, amount=100.00, txn_date=date(2026, 1, 10))
    txn_b = _make_txn(2, account_id=2, amount=-100.00, txn_date=date(2026, 1, 10))
    transfer_cat = _make_category(cat_id=10)

    session = MagicMock()
    session.scalar.side_effect = [transfer_cat, txn_b]
    session.scalars.return_value = iter([txn_a])

    detect_transfers(session, new_transaction_ids=[1])

    assert txn_a.status == TransactionStatus.transfer
    assert txn_a.category_id == 10
    assert txn_a.transfer_counterpart_id == 2
    assert txn_b.status == TransactionStatus.transfer
    assert txn_b.category_id == 10
    assert txn_b.transfer_counterpart_id == 1
    session.commit.assert_called_once()


def test_detect_transfers_no_match_leaves_pending():
    """Transaction with no counterpart stays pending; no commit."""
    txn_a = _make_txn(1, account_id=1, amount=100.00, txn_date=date(2026, 1, 10))
    transfer_cat = _make_category()

    session = MagicMock()
    session.scalar.side_effect = [transfer_cat, None]
    session.scalars.return_value = iter([txn_a])

    detect_transfers(session, new_transaction_ids=[1])

    assert txn_a.status == TransactionStatus.pending
    assert txn_a.transfer_counterpart_id is None
    session.commit.assert_not_called()


def test_detect_transfers_empty_ids_is_noop():
    """Empty new_transaction_ids → no DB queries, no error."""
    session = MagicMock()
    detect_transfers(session, new_transaction_ids=[])
    session.scalar.assert_not_called()
    session.commit.assert_not_called()


def test_detect_transfers_missing_category_skips():
    """No Transfer category in DB → graceful skip, transactions remain pending."""
    txn_a = _make_txn(1, account_id=1, amount=100.00, txn_date=date(2026, 1, 10))
    session = MagicMock()
    session.scalar.return_value = None  # category not found
    session.scalars.return_value = iter([txn_a])

    detect_transfers(session, new_transaction_ids=[1])

    assert txn_a.status == TransactionStatus.pending
    session.commit.assert_not_called()


def test_detect_transfers_same_account_not_matched():
    """Two transactions on same account with opposite amounts → not matched."""
    txn_a = _make_txn(1, account_id=1, amount=100.00, txn_date=date(2026, 1, 10))
    transfer_cat = _make_category()

    session = MagicMock()
    # Category found; scalar for counterpart returns None (same-account condition filters it out)
    session.scalar.side_effect = [transfer_cat, None]
    session.scalars.return_value = iter([txn_a])

    detect_transfers(session, new_transaction_ids=[1])

    assert txn_a.status == TransactionStatus.pending
    session.commit.assert_not_called()


def test_detect_transfers_amount_mismatch_not_matched():
    """Amount difference > $0.01 → no match, transaction stays pending."""
    txn_a = _make_txn(1, account_id=1, amount=100.00, txn_date=date(2026, 1, 10))
    transfer_cat = _make_category()

    session = MagicMock()
    session.scalar.side_effect = [transfer_cat, None]
    session.scalars.return_value = iter([txn_a])

    detect_transfers(session, new_transaction_ids=[1])

    assert txn_a.status == TransactionStatus.pending
    session.commit.assert_not_called()


def test_detect_transfers_date_gap_too_large_not_matched():
    """Transactions more than 3 days apart → not matched even with opposite amounts."""
    txn_a = _make_txn(1, account_id=1, amount=100.00, txn_date=date(2026, 1, 10))
    transfer_cat = _make_category()

    session = MagicMock()
    session.scalar.side_effect = [transfer_cat, None]  # category found, no counterpart (gap > 3 days)
    session.scalars.return_value = iter([txn_a])

    detect_transfers(session, new_transaction_ids=[1])

    assert txn_a.status == TransactionStatus.pending
    assert txn_a.transfer_counterpart_id is None
    session.commit.assert_not_called()


def test_detect_transfers_already_matched_skipped():
    """Both sides of a transfer in new_transaction_ids — txn_b skipped when already matched."""
    txn_a = _make_txn(1, account_id=1, amount=100.00, txn_date=date(2026, 1, 10))
    txn_b = _make_txn(2, account_id=2, amount=-100.00, txn_date=date(2026, 1, 10))
    transfer_cat = _make_category(cat_id=10)

    session = MagicMock()
    # category, then counterpart for txn_a (txn_b); txn_b is skipped — no more scalar calls
    session.scalar.side_effect = [transfer_cat, txn_b]
    session.scalars.return_value = iter([txn_a, txn_b])

    detect_transfers(session, new_transaction_ids=[1, 2])

    # Both tagged exactly once
    assert txn_a.status == TransactionStatus.transfer
    assert txn_b.status == TransactionStatus.transfer
    assert txn_a.transfer_counterpart_id == 2
    assert txn_b.transfer_counterpart_id == 1
    # Only 2 scalar calls: 1 for category + 1 for counterpart of txn_a; txn_b loop body skipped
    assert session.scalar.call_count == 2
    session.commit.assert_called_once()
