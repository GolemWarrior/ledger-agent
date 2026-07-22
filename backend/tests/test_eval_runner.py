"""Tests for eval/runner.py — CSV loading/validation and run_dataset determinism."""
from unittest.mock import MagicMock, patch

import pytest
from langgraph.errors import GraphInterrupt

from ledger_agent.eval.metrics import RowResult, compute_accuracy, compute_escalation_precision, compute_escalation_recall
from ledger_agent.eval.runner import DatasetRow, get_previous_run, load_dataset, print_report, run_dataset

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


def test_load_dataset_raises_value_error_on_missing_trailing_field(tmp_path):
    # Row is short one field (no trailing comma for is_genuinely_ambiguous) — DictReader
    # fills the missing key with None; loading must raise a clean ValueError, not crash.
    csv_path = _write_csv(tmp_path, "Whole Foods,42.00,2026-01-14,Groceries\n")

    with pytest.raises(ValueError, match="row 2"):
        load_dataset(csv_path, VALID_CATEGORIES)


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


def test_run_dataset_skips_row_that_raises_and_rolls_back():
    fake_account = MagicMock(name="Eval")

    def fake_add(obj):
        obj.account = fake_account

    session = MagicMock()
    session.add.side_effect = fake_add
    settings = MagicMock()
    mock_compiled = MagicMock()
    mock_compiled.invoke.side_effect = [None, RuntimeError("boom")]

    with patch("ledger_agent.eval.runner.build_graph") as mock_build:
        mock_build.return_value.compile.return_value = mock_compiled
        results = run_dataset(session, settings, _make_rows(), account_id=1)

    assert len(results) == 1
    assert results[0].was_escalated is False
    assert session.rollback.called


# --- get_previous_run ---

def test_get_previous_run_returns_the_scalar_result():
    fake_run = MagicMock(accuracy=0.91, escalation_precision=0.8, escalation_recall=0.7)
    session = MagicMock()
    session.scalar.return_value = fake_run

    result = get_previous_run(session)

    assert result is fake_run


def test_get_previous_run_returns_none_when_no_prior_runs():
    session = MagicMock()
    session.scalar.return_value = None

    result = get_previous_run(session)

    assert result is None


def test_get_previous_run_orders_by_run_at_descending():
    session = MagicMock()
    session.scalar.return_value = None

    get_previous_run(session)

    statement = session.scalar.call_args[0][0]
    assert "ORDER BY eval_runs.run_at DESC" in str(statement)


# --- print_report before/after comparison ---

def _make_results():
    return [
        RowResult(predicted_category="Groceries", correct_category="Groceries",
                  was_escalated=False, is_genuinely_ambiguous=False),
        RowResult(predicted_category=None, correct_category="Dining",
                  was_escalated=True, is_genuinely_ambiguous=True),
    ]


def test_print_report_shows_before_after_comparison_when_previous_run_exists(capsys):
    previous_run = MagicMock(accuracy=0.91, escalation_precision=0.80, escalation_recall=0.70)

    print_report(0.94, 0.85, 0.75, _make_results(), previous_run)

    out = capsys.readouterr().out
    assert "94.0%  (previous: 91.0%, +3.0)" in out
    assert "85.0%  (previous: 80.0%, +5.0)" in out
    assert "75.0%  (previous: 70.0%, +5.0)" in out


def test_print_report_shows_first_run_messaging_when_no_previous_run(capsys):
    print_report(0.94, 0.85, 0.75, _make_results(), None)

    out = capsys.readouterr().out
    assert out.count("(no previous run — this is the first recorded run)") == 3
    assert "0.0%" not in out


def test_print_report_shows_skipped_row_count(capsys):
    print_report(0.94, 0.85, 0.75, _make_results(), None, skipped_count=3)

    out = capsys.readouterr().out
    assert "(3 skipped due to errors)" in out


def test_print_report_omits_skipped_note_when_zero(capsys):
    print_report(0.94, 0.85, 0.75, _make_results(), None, skipped_count=0)

    out = capsys.readouterr().out
    assert "skipped" not in out
