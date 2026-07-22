"""Tests for eval/runner.py — CSV loading/validation and run_dataset determinism."""
from unittest.mock import MagicMock, patch

import pytest
from langgraph.errors import GraphInterrupt

from ledger_agent.eval.metrics import compute_accuracy, compute_escalation_precision, compute_escalation_recall
from ledger_agent.eval.runner import DatasetRow, load_dataset, run_dataset

VALID_CATEGORIES = {"Groceries", "Dining", "Transportation", "Utilities", "Housing",
                     "Healthcare", "Entertainment", "Shopping", "Transfer", "Uncategorized"}

CSV_HEADER = "description,amount,date,correct_category,is_genuinely_ambiguous,notes\n"


def _write_csv(tmp_path, body: str):
    path = tmp_path / "eval_dataset.csv"
    path.write_text(CSV_HEADER + body)
    return path


# --- load_dataset ---

def test_load_dataset_raises_on_invalid_correct_category(tmp_path):
    csv_path = _write_csv(tmp_path, "Whole Foods,42.00,2026-01-14,NotACategory,false,\n")

    with pytest.raises(ValueError, match="row 2"):
        load_dataset(csv_path, VALID_CATEGORIES)


def test_load_dataset_coerces_is_genuinely_ambiguous_to_bool(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "Amazon,49.99,2026-01-14,Shopping,true,\n"
        "Netflix,15.99,2026-01-15,Entertainment,false,\n",
    )

    rows = load_dataset(csv_path, VALID_CATEGORIES)

    assert rows[0].is_genuinely_ambiguous is True
    assert rows[1].is_genuinely_ambiguous is False
    assert isinstance(rows[0].is_genuinely_ambiguous, bool)


def test_load_dataset_parses_valid_rows(tmp_path):
    csv_path = _write_csv(tmp_path, "Whole Foods,42.00,2026-01-14,Groceries,false,\n")

    rows = load_dataset(csv_path, VALID_CATEGORIES)

    assert len(rows) == 1
    assert rows[0].description == "Whole Foods"
    assert rows[0].correct_category == "Groceries"


# --- run_dataset determinism (idempotency at metrics-computation level) ---

def _make_rows():
    from datetime import date
    from decimal import Decimal
    return [
        DatasetRow(description="A", amount=Decimal("10.00"), date=date(2026, 1, 1),
                   correct_category="Groceries", is_genuinely_ambiguous=False),
        DatasetRow(description="B", amount=Decimal("20.00"), date=date(2026, 1, 2),
                   correct_category="Dining", is_genuinely_ambiguous=True),
    ]


def _run_with_mocked_graph():
    fake_account = MagicMock(name="Eval")

    def fake_add(obj):
        obj.account = fake_account

    session = MagicMock()
    session.add.side_effect = fake_add
    settings = MagicMock()
    mock_compiled = MagicMock()
    mock_compiled.invoke.side_effect = [None, GraphInterrupt("question?")]

    with patch("ledger_agent.eval.runner.build_graph") as mock_build:
        mock_build.return_value.compile.return_value = mock_compiled
        results = run_dataset(session, settings, _make_rows(), account_id=1)

    return results


def test_run_dataset_is_idempotent_across_identical_runs():
    results_1 = _run_with_mocked_graph()
    results_2 = _run_with_mocked_graph()

    assert results_1 == results_2

    metrics_1 = (
        compute_accuracy(results_1),
        compute_escalation_precision(results_1),
        compute_escalation_recall(results_1),
    )
    metrics_2 = (
        compute_accuracy(results_2),
        compute_escalation_precision(results_2),
        compute_escalation_recall(results_2),
    )
    assert metrics_1 == metrics_2


def test_run_dataset_marks_graph_interrupt_rows_as_escalated():
    results = _run_with_mocked_graph()

    assert results[0].was_escalated is False
    assert results[1].was_escalated is True
