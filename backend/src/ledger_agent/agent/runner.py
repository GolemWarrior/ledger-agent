import logging
from datetime import UTC, datetime

from langgraph.errors import GraphInterrupt
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker, selectinload

from ledger_agent.db.models import SyncRun, SyncRunStatus, Transaction, TransactionStatus
from ledger_agent.agent.graph import build_graph

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.80


def _get_psycopg_conn_string(database_url_sync: str) -> str:
    """Convert SQLAlchemy URL to psycopg3-compatible connection string for PostgresSaver."""
    return database_url_sync.replace("postgresql+psycopg://", "postgresql://")


def _txn_to_state(txn: Transaction) -> dict:
    return {
        "transaction_id": txn.id,
        "description": txn.description,
        "merchant_name": txn.merchant_name,
        "amount_str": str(txn.amount),
        "date_str": txn.date.isoformat(),
        "account_name": txn.account.name,
        "vendor_memory_hit": None,
        "category_name": None,
        "confidence": None,
        "reasoning_trace": None,
        "escalation_question": None,
    }


def _mark_complete(session: Session, sync_run_id: int) -> None:
    sync_run = session.get(SyncRun, sync_run_id)
    if sync_run and sync_run.status == SyncRunStatus.processing:
        sync_run.status = SyncRunStatus.complete
        sync_run.finished_at = datetime.now(UTC)
        session.commit()


def _mark_error(session: Session, sync_run_id: int, error: str) -> None:
    sync_run = session.get(SyncRun, sync_run_id)
    if sync_run and sync_run.status == SyncRunStatus.processing:
        sync_run.status = SyncRunStatus.error
        sync_run.error = error
        sync_run.finished_at = datetime.now(UTC)
        session.commit()


def run_classification_agent(session_factory: sessionmaker, sync_run_id: int | None = None) -> None:
    """Background thread: classify all pending transactions using LangGraph.

    Args:
        session_factory: sync session factory (NOT async — background thread only)
        sync_run_id: if provided, marks this SyncRun complete/error when done.
                     Pass None for startup-resume (no SyncRun to update).
    """
    from ledger_agent.config import settings

    with session_factory() as session:
        try:
            # If triggered from sync, check if sync itself failed — skip agent if so
            if sync_run_id is not None:
                sync_run = session.get(SyncRun, sync_run_id)
                if sync_run and sync_run.status == SyncRunStatus.error:
                    logger.info("Sync run %s failed — skipping classification agent", sync_run_id)
                    return

            pending_txns = list(session.scalars(
                select(Transaction)
                .where(Transaction.status == TransactionStatus.pending)
                .options(selectinload(Transaction.account))
            ))

            if not pending_txns:
                logger.info("No pending transactions — nothing to classify")
                if sync_run_id is not None:
                    _mark_complete(session, sync_run_id)
                return

            logger.info("Classifying %d pending transaction(s)", len(pending_txns))

            conn_string = _get_psycopg_conn_string(settings.database_url_sync)

            from langgraph.checkpoint.postgres import PostgresSaver
            with PostgresSaver.from_conn_string(conn_string) as checkpointer:
                checkpointer.setup()
                compiled = build_graph(session, settings).compile(checkpointer=checkpointer)

                for txn in pending_txns:
                    thread_config = {"configurable": {"thread_id": f"txn-{txn.id}"}}
                    initial_state = _txn_to_state(txn)
                    try:
                        compiled.invoke(initial_state, config=thread_config)
                    except GraphInterrupt:
                        logger.info(
                            "Transaction %s escalated — waiting for user resolution", txn.id
                        )
                    except Exception:
                        logger.exception(
                            "Classification failed for transaction %s — skipping", txn.id
                        )
                        # Continue processing other transactions

            if sync_run_id is not None:
                _mark_complete(session, sync_run_id)
            logger.info("Classification agent complete")

        except Exception as e:
            logger.exception("Classification agent batch failed")
            if sync_run_id is not None:
                try:
                    _mark_error(session, sync_run_id, str(e))
                except Exception:
                    logger.exception("Failed to write agent error to DB")
