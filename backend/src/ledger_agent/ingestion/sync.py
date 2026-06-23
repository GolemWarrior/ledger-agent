import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ledger_agent.db.models import (
    Account, Category, SyncRun, SyncRunStatus, Transaction, TransactionStatus,
)
from ledger_agent.ingestion.plaid_client import fetch_transactions

logger = logging.getLogger(__name__)


def detect_transfers(session: Session, new_transaction_ids: list[int]) -> None:
    """Tag cross-account transfer pairs among newly written transactions.

    Runs after all accounts are processed in a sync. For each new pending
    transaction, searches ALL pending transactions (new and pre-existing) for
    a counterpart on a different account with opposite amount (±$0.01) within
    a 3-day window. When found, both are tagged as transfer.
    """
    if not new_transaction_ids:
        return

    transfer_category = session.scalar(
        select(Category).where(Category.name == "Transfer")
    )
    if transfer_category is None:
        logger.warning("Transfer category not found — skipping transfer detection")
        return

    new_txns = list(session.scalars(
        select(Transaction).where(
            Transaction.id.in_(new_transaction_ids),
            Transaction.status == TransactionStatus.pending,
        )
    ))

    matched_ids: set[int] = set()

    for txn in new_txns:
        if txn.id in matched_ids:
            continue

        window_start = txn.date - timedelta(days=3)
        window_end = txn.date + timedelta(days=3)

        conditions = [
            Transaction.account_id != txn.account_id,
            Transaction.status == TransactionStatus.pending,
            Transaction.date >= window_start,
            Transaction.date <= window_end,
            func.abs(Transaction.amount + txn.amount) <= Decimal("0.01"),
        ]
        if matched_ids:
            conditions.append(Transaction.id.notin_(matched_ids))

        counterpart = session.scalar(select(Transaction).where(*conditions))

        if counterpart is not None:
            txn.status = TransactionStatus.transfer
            txn.category_id = transfer_category.id
            txn.transfer_counterpart_id = counterpart.id

            counterpart.status = TransactionStatus.transfer
            counterpart.category_id = transfer_category.id
            counterpart.transfer_counterpart_id = txn.id

            matched_ids.add(txn.id)
            matched_ids.add(counterpart.id)

    if matched_ids:
        session.commit()


def run_full_sync(
    session_factory: sessionmaker[Session],
    plaid_client,
    sync_run_id: int,
) -> None:
    """Background thread: pull transactions for all accounts, write to DB.

    Uses sync Session — NEVER called from an async context or shared with AsyncSession pool.
    All exceptions are caught and written to sync_runs.error — never propagated.
    """
    with session_factory() as session:
        sync_run = session.get(SyncRun, sync_run_id)
        if sync_run is None:
            logger.error("SyncRun %s not found — aborting sync", sync_run_id)
            return
        try:
            accounts = list(session.scalars(select(Account)))
            total_fetched = 0
            total_written = 0
            new_transaction_ids: list[int] = []

            for account in accounts:
                if account.last_synced_at:
                    start_date = account.last_synced_at.date()
                else:
                    start_date = date.today() - timedelta(days=90)
                end_date = date.today()

                try:
                    plaid_txns = fetch_transactions(
                        plaid_client, account.access_token, start_date, end_date
                    )
                except Exception:
                    logger.exception("Plaid fetch failed for account %s", account.id)
                    raise

                total_fetched += len(plaid_txns)

                for txn in plaid_txns:
                    existing = session.scalar(
                        select(Transaction).where(
                            Transaction.plaid_transaction_id == txn["plaid_transaction_id"]
                        )
                    )
                    if existing is None:
                        new_txn = Transaction(
                            plaid_transaction_id=txn["plaid_transaction_id"],
                            account_id=account.id,
                            description=txn["description"],
                            merchant_name=txn["merchant_name"],
                            amount=txn["amount"],
                            date=txn["date"],
                            status=TransactionStatus.pending,
                        )
                        session.add(new_txn)
                        session.flush()
                        new_transaction_ids.append(new_txn.id)
                        total_written += 1

                account.last_synced_at = datetime.now(UTC)
                sync_run.processed = total_written
                sync_run.total = total_fetched
                session.commit()

            detect_transfers(session, new_transaction_ids)

            # run_classification_agent (called after this function) is responsible for marking complete
            logger.info("Sync complete: %d written / %d fetched", total_written, total_fetched)

        except Exception as e:
            logger.exception("Sync failed")
            try:
                sync_run.status = SyncRunStatus.error
                sync_run.error = str(e)
                sync_run.finished_at = datetime.now(UTC)
                session.commit()
            except Exception:
                logger.exception("Failed to write sync error to DB")
