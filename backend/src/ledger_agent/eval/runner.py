"""python -m ledger_agent.eval.runner

Runs the Classification Agent against eval_dataset.csv inside an isolated
`eval` Postgres schema and reports accuracy / escalation precision / recall.
"""
import csv
import hashlib
import inspect
import logging
from dataclasses import dataclass
from datetime import date as date_cls
from decimal import Decimal, InvalidOperation
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphInterrupt
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from ledger_agent.agent.graph import build_graph
from ledger_agent.agent.prompts import build_classification_prompt
from ledger_agent.agent.runner import _txn_to_state
from ledger_agent.db import eval_models  # noqa: F401 — registers EvalRun on Base.metadata
from ledger_agent.db.base import Base
from ledger_agent.db.eval_models import EvalRun
from ledger_agent.db.models import Account, Category, Transaction, TransactionStatus
from ledger_agent.db.seed import DEFAULT_CATEGORIES
from ledger_agent.eval.metrics import (
    RowResult,
    compute_accuracy,
    compute_escalation_precision,
    compute_escalation_recall,
)

logger = logging.getLogger(__name__)

EVAL_DATASET_PATH = Path(__file__).resolve().parents[4] / "eval_dataset.csv"
DUMMY_ACCOUNT_NAME = "Eval"


@dataclass
class DatasetRow:
    description: str
    amount: Decimal
    date: date_cls
    correct_category: str
    is_genuinely_ambiguous: bool


def ensure_eval_schema(engine) -> None:
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS eval"))
        conn.commit()
    Base.metadata.create_all(engine, checkfirst=True)


def reset_eval_schema(session: Session) -> None:
    session.execute(text("TRUNCATE transactions, vendor_memory, resolutions RESTART IDENTITY CASCADE"))
    session.commit()


def seed_categories(session: Session) -> None:
    count = session.scalar(select(Category).limit(1))
    if count is None:
        session.add_all([Category(name=name) for name in DEFAULT_CATEGORIES])
        session.commit()


def ensure_dummy_account(session: Session) -> Account:
    account = session.scalar(select(Account).where(Account.name == DUMMY_ACCOUNT_NAME))
    if account is None:
        account = Account(
            plaid_account_id="eval-dummy",
            name=DUMMY_ACCOUNT_NAME,
            type="checking",
            access_token="eval-dummy-token",
            item_id="eval-dummy-item",
        )
        session.add(account)
        session.commit()
        session.refresh(account)
    return account


REQUIRED_CSV_COLUMNS = {"description", "amount", "date", "correct_category", "is_genuinely_ambiguous"}


def load_dataset(csv_path: Path, valid_categories: set[str]) -> list[DatasetRow]:
    if not csv_path.exists():
        raise FileNotFoundError(f"eval dataset not found: {csv_path}")

    rows: list[DatasetRow] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing_columns = REQUIRED_CSV_COLUMNS - set(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(f"eval_dataset.csv is missing required columns: {sorted(missing_columns)}")

        for line_num, row in enumerate(reader, start=2):
            correct_category = row["correct_category"]
            if correct_category not in valid_categories:
                raise ValueError(
                    f"eval_dataset.csv row {line_num}: invalid correct_category {correct_category!r}"
                )
            try:
                amount = Decimal(row["amount"])
                date = date_cls.fromisoformat(row["date"])
                is_genuinely_ambiguous = row["is_genuinely_ambiguous"].strip().lower() == "true"
            except (InvalidOperation, ValueError, AttributeError, TypeError) as exc:
                raise ValueError(f"eval_dataset.csv row {line_num}: {exc}") from exc
            rows.append(DatasetRow(
                description=row["description"],
                amount=amount,
                date=date,
                correct_category=correct_category,
                is_genuinely_ambiguous=is_genuinely_ambiguous,
            ))

    if not rows:
        raise ValueError(f"eval_dataset.csv has no data rows: {csv_path}")

    return rows


def run_dataset(session: Session, settings, rows: list[DatasetRow], account_id: int) -> list[RowResult]:
    compiled = build_graph(session, settings).compile(checkpointer=MemorySaver())

    results: list[RowResult] = []
    skipped_count = 0
    for idx, row in enumerate(rows):
        was_escalated = False
        try:
            txn = Transaction(
                plaid_transaction_id=f"eval-{idx}",
                account_id=account_id,
                description=row.description,
                amount=row.amount,
                date=row.date,
                status=TransactionStatus.pending,
            )
            session.add(txn)
            session.commit()
            session.refresh(txn)

            thread_config = {"configurable": {"thread_id": f"eval-txn-{txn.id}"}}
            try:
                compiled.invoke(_txn_to_state(txn), config=thread_config)
            except GraphInterrupt:
                was_escalated = True

            session.refresh(txn)
            if txn.status == TransactionStatus.escalated:
                was_escalated = True

            predicted_category = txn.category.name if txn.category_id else None
        except Exception:
            logger.exception("eval row %d (%s) failed, skipping", idx, row.description)
            session.rollback()
            skipped_count += 1
            continue

        results.append(RowResult(
            predicted_category=predicted_category,
            correct_category=row.correct_category,
            was_escalated=was_escalated,
            is_genuinely_ambiguous=row.is_genuinely_ambiguous,
        ))

    if skipped_count:
        logger.warning("eval run: %d/%d rows skipped due to errors", skipped_count, len(rows))

    return results


def get_previous_run(session: Session) -> EvalRun | None:
    return session.scalar(select(EvalRun).order_by(EvalRun.run_at.desc()).limit(1))


def _format_comparison(label: str, current: float, previous_value: float | None) -> str:
    if previous_value is None:
        return f"  {label}{current * 100:.1f}%  (no previous run — this is the first recorded run)"
    delta = (current - previous_value) * 100
    return f"  {label}{current * 100:.1f}%  (previous: {previous_value * 100:.1f}%, {delta:+.1f})"


def print_report(
    accuracy: float | None,
    precision: float | None,
    recall: float | None,
    results: list[RowResult],
    previous_run: EvalRun | None = None,
    skipped_count: int = 0,
) -> None:
    row_count = len(results)
    auto_resolved_count = sum(1 for r in results if not r.was_escalated)
    ambiguous_count = sum(1 for r in results if r.is_genuinely_ambiguous)
    escalated_count = sum(1 for r in results if r.was_escalated)

    print(f"Eval run — {row_count} rows" + (f" ({skipped_count} skipped due to errors)" if skipped_count else ""))
    if auto_resolved_count == 0:
        print("  Accuracy:              undefined (all rows escalated)")
    else:
        print(_format_comparison(
            "Accuracy:              ", accuracy,
            previous_run.accuracy if previous_run else None,
        ))
    if escalated_count == 0:
        print("  Escalation precision:  undefined (no rows escalated)")
    else:
        print(_format_comparison(
            "Escalation precision:  ", precision,
            previous_run.escalation_precision if previous_run else None,
        ))
    if ambiguous_count == 0:
        print("  Escalation recall:     undefined (no genuinely-ambiguous rows)")
    else:
        print(_format_comparison(
            "Escalation recall:     ", recall,
            previous_run.escalation_recall if previous_run else None,
        ))


def main() -> None:
    from ledger_agent.config import settings

    engine = create_engine(settings.database_url_eval)
    ensure_eval_schema(engine)
    session_factory = sessionmaker(engine)

    with session_factory() as session:
        reset_eval_schema(session)
        seed_categories(session)
        account = ensure_dummy_account(session)

        rows = load_dataset(EVAL_DATASET_PATH, set(DEFAULT_CATEGORIES))
        previous_run = get_previous_run(session)
        results = run_dataset(session, settings, rows, account.id)

        accuracy = compute_accuracy(results)
        precision = compute_escalation_precision(results)
        recall = compute_escalation_recall(results)

        print_report(accuracy, precision, recall, results, previous_run, skipped_count=len(rows) - len(results))

        prompt_hash = hashlib.sha256(
            inspect.getsource(build_classification_prompt).encode()
        ).hexdigest()[:12]
        session.add(EvalRun(
            model_version=settings.anthropic_model,
            prompt_hash=prompt_hash,
            accuracy=accuracy,
            escalation_precision=precision,
            escalation_recall=recall,
        ))
        session.commit()


if __name__ == "__main__":
    main()
