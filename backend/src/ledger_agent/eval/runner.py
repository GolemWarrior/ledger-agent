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
from decimal import Decimal
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


def load_dataset(csv_path: Path, valid_categories: set[str]) -> list[DatasetRow]:
    rows: list[DatasetRow] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for line_num, row in enumerate(reader, start=2):
            correct_category = row["correct_category"]
            if correct_category not in valid_categories:
                raise ValueError(
                    f"eval_dataset.csv row {line_num}: invalid correct_category {correct_category!r}"
                )
            rows.append(DatasetRow(
                description=row["description"],
                amount=Decimal(row["amount"]),
                date=date_cls.fromisoformat(row["date"]),
                correct_category=correct_category,
                is_genuinely_ambiguous=row["is_genuinely_ambiguous"].strip().lower() == "true",
            ))
    return rows


def run_dataset(session: Session, settings, rows: list[DatasetRow], account_id: int) -> list[RowResult]:
    compiled = build_graph(session, settings).compile(checkpointer=MemorySaver())

    results: list[RowResult] = []
    for idx, row in enumerate(rows):
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

        was_escalated = False
        thread_config = {"configurable": {"thread_id": f"eval-txn-{txn.id}"}}
        try:
            compiled.invoke(_txn_to_state(txn), config=thread_config)
        except GraphInterrupt:
            was_escalated = True

        session.refresh(txn)
        if txn.status == TransactionStatus.escalated:
            was_escalated = True

        predicted_category = txn.category.name if txn.category_id else None
        results.append(RowResult(
            predicted_category=predicted_category,
            correct_category=row.correct_category,
            was_escalated=was_escalated,
            is_genuinely_ambiguous=row.is_genuinely_ambiguous,
        ))

    return results


def print_report(accuracy: float, precision: float, recall: float, row_count: int) -> None:
    print(f"Eval run — {row_count} rows")
    print(f"  Accuracy:              {accuracy * 100:.1f}%")
    print(f"  Escalation precision:  {precision * 100:.1f}%")
    print(f"  Escalation recall:     {recall * 100:.1f}%")


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
        results = run_dataset(session, settings, rows, account.id)

        accuracy = compute_accuracy(results)
        precision = compute_escalation_precision(results)
        recall = compute_escalation_recall(results)

        print_report(accuracy, precision, recall, len(results))

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
