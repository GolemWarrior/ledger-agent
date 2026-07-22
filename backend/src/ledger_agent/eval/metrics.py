from dataclasses import dataclass


@dataclass
class RowResult:
    predicted_category: str | None
    correct_category: str
    was_escalated: bool
    is_genuinely_ambiguous: bool


def compute_accuracy(results: list[RowResult]) -> float | None:
    """% of non-escalated rows where predicted_category == correct_category. None if undefined."""
    auto_resolved = [r for r in results if not r.was_escalated]
    if not auto_resolved:
        return None
    correct = sum(1 for r in auto_resolved if r.predicted_category == r.correct_category)
    return correct / len(auto_resolved)


def compute_escalation_recall(results: list[RowResult]) -> float | None:
    """% of genuinely-ambiguous rows that were escalated. None if undefined."""
    ambiguous = [r for r in results if r.is_genuinely_ambiguous]
    if not ambiguous:
        return None
    escalated = sum(1 for r in ambiguous if r.was_escalated)
    return escalated / len(ambiguous)


def compute_escalation_precision(results: list[RowResult]) -> float | None:
    """% of escalated rows that were genuinely ambiguous. None if undefined."""
    escalated = [r for r in results if r.was_escalated]
    if not escalated:
        return None
    ambiguous = sum(1 for r in escalated if r.is_genuinely_ambiguous)
    return ambiguous / len(escalated)
