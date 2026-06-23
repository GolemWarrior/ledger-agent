"""Tests for agent/runner.py — run_classification_agent."""
from unittest.mock import MagicMock, call, patch

from ledger_agent.agent.runner import _get_psycopg_conn_string, _txn_to_state, run_classification_agent
from ledger_agent.db.models import SyncRunStatus, TransactionStatus


# --- _get_psycopg_conn_string ---

def test_strips_psycopg_driver_prefix():
    url = "postgresql+psycopg://user:pass@localhost:5432/ledger"
    assert _get_psycopg_conn_string(url) == "postgresql://user:pass@localhost:5432/ledger"


def test_leaves_plain_postgresql_url_unchanged():
    url = "postgresql://user:pass@localhost:5432/ledger"
    assert _get_psycopg_conn_string(url) == url


# --- _txn_to_state ---

def test_txn_to_state_uses_str_amount():
    from decimal import Decimal
    txn = MagicMock()
    txn.id = 42
    txn.description = "STARBUCKS"
    txn.merchant_name = "Starbucks"
    txn.amount = Decimal("5.75")
    txn.date = MagicMock()
    txn.date.isoformat.return_value = "2026-01-15"
    txn.account.name = "Checking"

    state = _txn_to_state(txn)

    assert state["amount_str"] == "5.75"
    assert state["transaction_id"] == 42
    assert state["escalation_question"] is None


# --- run_classification_agent ---

def _make_session_factory(session):
    factory = MagicMock()
    factory.return_value.__enter__ = MagicMock(return_value=session)
    factory.return_value.__exit__ = MagicMock(return_value=False)
    return factory


def test_skips_agent_when_sync_run_errored():
    sync_run = MagicMock()
    sync_run.status = SyncRunStatus.error

    session = MagicMock()
    session.get.return_value = sync_run

    factory = _make_session_factory(session)

    with patch("ledger_agent.config.settings"):
        run_classification_agent(factory, sync_run_id=1)

    # scalars (pending txns query) should never be called
    session.scalars.assert_not_called()


def test_marks_complete_when_no_pending_transactions():
    sync_run = MagicMock()
    sync_run.status = SyncRunStatus.processing

    session = MagicMock()
    session.get.return_value = sync_run
    session.scalars.return_value = iter([])

    factory = _make_session_factory(session)

    with patch("ledger_agent.config.settings"):
        run_classification_agent(factory, sync_run_id=1)

    assert sync_run.status == SyncRunStatus.complete
    session.commit.assert_called()


def test_no_sync_run_update_when_sync_run_id_is_none():
    session = MagicMock()
    session.scalars.return_value = iter([])

    factory = _make_session_factory(session)

    with patch("ledger_agent.config.settings"):
        run_classification_agent(factory, sync_run_id=None)

    # get() should never be called when sync_run_id is None
    session.get.assert_not_called()


def test_classifies_pending_transactions_and_marks_complete():
    sync_run = MagicMock()
    sync_run.status = SyncRunStatus.processing

    txn = MagicMock()
    txn.id = 7
    txn.description = "WHOLE FOODS"
    txn.merchant_name = "Whole Foods"
    from decimal import Decimal
    txn.amount = Decimal("45.00")
    txn.date = MagicMock()
    txn.date.isoformat.return_value = "2026-01-20"
    txn.account.name = "Checking"

    session = MagicMock()
    session.get.return_value = sync_run
    session.scalars.return_value = iter([txn])

    factory = _make_session_factory(session)

    mock_compiled = MagicMock()

    with (
        patch("ledger_agent.config.settings") as mock_settings,
        patch("ledger_agent.agent.runner.build_graph") as mock_build,
        patch("langgraph.checkpoint.postgres.PostgresSaver") as mock_saver,
    ):
        mock_settings.database_url_sync = "postgresql+psycopg://u:p@db/ledger"
        mock_build.return_value.compile.return_value = mock_compiled
        mock_saver.from_conn_string.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_saver.from_conn_string.return_value.__exit__ = MagicMock(return_value=False)

        run_classification_agent(factory, sync_run_id=1)

    mock_compiled.invoke.assert_called_once()
    call_args = mock_compiled.invoke.call_args
    assert call_args[1]["config"]["configurable"]["thread_id"] == "txn-7"
    assert sync_run.status == SyncRunStatus.complete


def test_continues_after_per_transaction_exception():
    """A failed transaction must not prevent subsequent transactions from being classified."""
    sync_run = MagicMock()
    sync_run.status = SyncRunStatus.processing

    txn1 = MagicMock()
    txn1.id = 1
    txn2 = MagicMock()
    txn2.id = 2
    for txn in (txn1, txn2):
        from decimal import Decimal
        txn.amount = Decimal("10.00")
        txn.description = "DESC"
        txn.merchant_name = None
        txn.date = MagicMock()
        txn.date.isoformat.return_value = "2026-01-01"
        txn.account.name = "Checking"

    session = MagicMock()
    session.get.return_value = sync_run
    session.scalars.return_value = iter([txn1, txn2])

    factory = _make_session_factory(session)

    mock_compiled = MagicMock()
    mock_compiled.invoke.side_effect = [RuntimeError("LLM exploded"), None]

    with (
        patch("ledger_agent.config.settings") as mock_settings,
        patch("ledger_agent.agent.runner.build_graph") as mock_build,
        patch("langgraph.checkpoint.postgres.PostgresSaver") as mock_saver,
    ):
        mock_settings.database_url_sync = "postgresql+psycopg://u:p@db/ledger"
        mock_build.return_value.compile.return_value = mock_compiled
        mock_saver.from_conn_string.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_saver.from_conn_string.return_value.__exit__ = MagicMock(return_value=False)

        run_classification_agent(factory, sync_run_id=1)

    assert mock_compiled.invoke.call_count == 2
    assert sync_run.status == SyncRunStatus.complete
