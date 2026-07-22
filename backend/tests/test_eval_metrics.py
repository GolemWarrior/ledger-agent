"""Tests for eval/metrics.py — pure metric functions."""
from ledger_agent.eval.metrics import (
    RowResult,
    compute_accuracy,
    compute_escalation_precision,
    compute_escalation_recall,
)


def _row(predicted=None, correct="Groceries", escalated=False, ambiguous=False):
    return RowResult(
        predicted_category=predicted,
        correct_category=correct,
        was_escalated=escalated,
        is_genuinely_ambiguous=ambiguous,
    )


# --- compute_accuracy ---

def test_accuracy_all_correct():
    results = [_row(predicted="Groceries"), _row(predicted="Dining", correct="Dining")]
    assert compute_accuracy(results) == 1.0


def test_accuracy_all_wrong():
    results = [_row(predicted="Dining", correct="Groceries"), _row(predicted="Shopping", correct="Dining")]
    assert compute_accuracy(results) == 0.0


def test_accuracy_mixed():
    results = [
        _row(predicted="Groceries", correct="Groceries"),
        _row(predicted="Dining", correct="Groceries"),
    ]
    assert compute_accuracy(results) == 0.5


def test_accuracy_excludes_escalated_rows():
    results = [
        _row(predicted="Groceries", correct="Groceries"),
        _row(predicted=None, correct="Dining", escalated=True),
    ]
    assert compute_accuracy(results) == 1.0


def test_accuracy_all_escalated_returns_none():
    results = [_row(predicted=None, escalated=True), _row(predicted=None, escalated=True)]
    assert compute_accuracy(results) is None


# --- compute_escalation_recall ---

def test_escalation_recall_all_ambiguous_escalated():
    results = [_row(ambiguous=True, escalated=True), _row(ambiguous=True, escalated=True)]
    assert compute_escalation_recall(results) == 1.0


def test_escalation_recall_none_escalated():
    results = [_row(ambiguous=True, escalated=False), _row(ambiguous=True, escalated=False)]
    assert compute_escalation_recall(results) == 0.0


def test_escalation_recall_zero_ambiguous_rows_returns_none():
    results = [_row(ambiguous=False, escalated=False), _row(ambiguous=False, escalated=True)]
    assert compute_escalation_recall(results) is None


def test_escalation_recall_mixed():
    results = [
        _row(ambiguous=True, escalated=True),
        _row(ambiguous=True, escalated=False),
    ]
    assert compute_escalation_recall(results) == 0.5


# --- compute_escalation_precision ---

def test_escalation_precision_all_escalated_ambiguous():
    results = [_row(ambiguous=True, escalated=True), _row(ambiguous=True, escalated=True)]
    assert compute_escalation_precision(results) == 1.0


def test_escalation_precision_none_escalated_returns_none():
    results = [_row(ambiguous=True, escalated=False), _row(ambiguous=False, escalated=False)]
    assert compute_escalation_precision(results) is None


def test_escalation_precision_mixed():
    results = [
        _row(ambiguous=True, escalated=True),
        _row(ambiguous=False, escalated=True),
    ]
    assert compute_escalation_precision(results) == 0.5
