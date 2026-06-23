from unittest.mock import MagicMock, patch

from ledger_agent.agent.nodes import ClassificationState, auto_resolve_node, classify_node, escalate_node, gate, lookup_node
from ledger_agent.agent.prompts import build_classification_prompt, parse_llm_response
from ledger_agent.db.models import TransactionStatus


# --- Fixtures ---

def _make_state(confidence=None, merchant_name=None, category_name="Groceries") -> ClassificationState:
    return {
        "transaction_id": 1,
        "description": "WHOLE FOODS MARKET",
        "merchant_name": merchant_name,
        "amount_str": "52.30",
        "date_str": "2026-01-15",
        "account_name": "Checking",
        "vendor_memory_hit": None,
        "category_name": category_name,
        "confidence": confidence,
        "reasoning_trace": None,
        "escalation_question": None,
    }


def _make_vm_hit(category_name="Groceries", hit_count=3):
    hit = MagicMock()
    hit.vendor = "WHOLE FOODS MARKET"
    hit.hit_count = hit_count
    hit.category = MagicMock()
    hit.category.name = category_name
    return hit


def _make_category(cat_id=1, name="Groceries"):
    cat = MagicMock()
    cat.id = cat_id
    cat.name = name
    return cat


# --- gate tests ---

def test_gate_auto_resolve_on_high_confidence():
    state = _make_state(confidence=0.80)
    assert gate(state) == "auto_resolve"


def test_gate_auto_resolve_on_perfect_confidence():
    state = _make_state(confidence=1.0)
    assert gate(state) == "auto_resolve"


def test_gate_escalate_on_low_confidence():
    state = _make_state(confidence=0.79)
    assert gate(state) == "escalate"


def test_gate_escalate_on_zero_confidence():
    state = _make_state(confidence=0.0)
    assert gate(state) == "escalate"


def test_gate_escalate_on_none_confidence():
    state = _make_state(confidence=None)
    assert gate(state) == "escalate"


# --- parse_llm_response tests ---

def test_parse_llm_response_valid_json():
    text = '{"category": "Groceries", "confidence": 0.95, "reasoning": "Food store"}'
    result = parse_llm_response(text)
    assert result["category"] == "Groceries"
    assert result["confidence"] == 0.95
    assert result["reasoning"] == "Food store"


def test_parse_llm_response_strips_markdown_fences():
    text = '```json\n{"category": "Dining", "confidence": 0.88, "reasoning": "Restaurant"}\n```'
    result = parse_llm_response(text)
    assert result["category"] == "Dining"


# --- lookup_node tests ---

def test_lookup_node_returns_hit_when_vendor_exists():
    hit = _make_vm_hit()
    session = MagicMock()
    session.scalar.return_value = hit
    state = _make_state(merchant_name="WHOLE FOODS MARKET")

    result = lookup_node(state, session)

    assert result["vendor_memory_hit"]["category"] == "Groceries"
    assert result["vendor_memory_hit"]["hit_count"] == 3


def test_lookup_node_returns_none_when_no_vendor():
    session = MagicMock()
    session.scalar.return_value = None
    state = _make_state()

    result = lookup_node(state, session)

    assert result["vendor_memory_hit"] is None


def test_lookup_node_falls_back_to_description_when_no_merchant():
    session = MagicMock()
    session.scalar.return_value = None
    state = _make_state(merchant_name=None)

    lookup_node(state, session)

    # Should have called scalar with description[:50]
    session.scalar.assert_called_once()


# --- classify_node tests ---

def test_classify_node_calls_anthropic_and_parses_response():
    session = MagicMock()
    session.scalars.return_value = iter([_make_category(name="Groceries")])

    settings = MagicMock()
    settings.anthropic_api_key = "test-key"
    settings.anthropic_model = "claude-haiku-4-5-20251001"

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = '{"category": "Groceries", "confidence": 0.92, "reasoning": "Supermarket purchase"}'

    with patch("ledger_agent.agent.nodes.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = mock_response
        state = _make_state()
        result = classify_node(state, session, settings)

    assert result["category_name"] == "Groceries"
    assert result["confidence"] == 0.92
    assert "Supermarket" in result["reasoning_trace"]


# --- auto_resolve_node tests ---

def test_auto_resolve_node_writes_resolved_status():
    category = _make_category(cat_id=5, name="Groceries")
    txn = MagicMock()
    txn.id = 1

    session = MagicMock()
    session.scalar.return_value = category
    session.get.return_value = txn

    state = _make_state(confidence=0.92)
    state["reasoning_trace"] = "Supermarket"
    auto_resolve_node(state, session)

    assert txn.status == TransactionStatus.resolved
    assert txn.category_id == 5
    assert txn.confidence_score == 0.92
    assert txn.reasoning_trace == "Supermarket"
    session.commit.assert_called_once()


def test_auto_resolve_node_falls_back_to_uncategorized_when_category_not_found():
    uncategorized = _make_category(cat_id=10, name="Uncategorized")
    txn = MagicMock()

    session = MagicMock()
    session.scalar.side_effect = [None, uncategorized]  # first: category not found; second: Uncategorized
    session.get.return_value = txn

    state = _make_state(confidence=0.85, category_name="NonExistentCategory")
    state["reasoning_trace"] = "test"
    auto_resolve_node(state, session)

    assert txn.category_id == 10
    session.commit.assert_called_once()


# --- build_classification_prompt tests ---

def test_build_classification_prompt_includes_categories():
    categories = [
        {"name": "Groceries", "hint": "food and household supplies"},
        {"name": "Dining", "hint": None},
    ]
    state = _make_state()
    prompt = build_classification_prompt(state, categories)

    assert "Groceries" in prompt
    assert "food and household supplies" in prompt
    assert "Dining" in prompt


def test_build_classification_prompt_includes_vendor_memory():
    categories = [{"name": "Groceries", "hint": None}]
    state = _make_state()
    vm_hit = {"vendor": "WHOLE FOODS", "category": "Groceries", "hit_count": 5}
    prompt = build_classification_prompt(state, categories, vendor_memory_hit=vm_hit)

    assert "previously classified" in prompt
    assert "Groceries" in prompt
    assert "5" in prompt


def test_build_classification_prompt_no_vendor_memory_when_none():
    categories = [{"name": "Groceries", "hint": None}]
    state = _make_state()
    prompt = build_classification_prompt(state, categories, vendor_memory_hit=None)

    assert "previously classified" not in prompt


# --- escalate_node tests ---

def test_escalate_node_writes_escalated_status():
    txn = MagicMock()
    session = MagicMock()
    session.get.return_value = txn

    state = _make_state(confidence=0.65)
    state["escalation_question"] = "Is this a business or personal expense?"

    with patch("ledger_agent.agent.nodes.interrupt"):
        escalate_node(state, session)

    assert txn.status == TransactionStatus.escalated
    assert txn.escalation_question == "Is this a business or personal expense?"
    session.commit.assert_called_once()


def test_escalate_node_uses_fallback_question_when_none():
    txn = MagicMock()
    session = MagicMock()
    session.get.return_value = txn

    state = _make_state(confidence=0.65)
    state["escalation_question"] = None

    with patch("ledger_agent.agent.nodes.interrupt"):
        escalate_node(state, session)

    assert "category" in txn.escalation_question.lower()


def test_escalate_node_calls_interrupt_with_question():
    txn = MagicMock()
    session = MagicMock()
    session.get.return_value = txn

    state = _make_state(confidence=0.65)
    state["escalation_question"] = "Is this dining or entertainment?"

    with patch("ledger_agent.agent.nodes.interrupt") as mock_interrupt:
        escalate_node(state, session)
        mock_interrupt.assert_called_once_with("Is this dining or entertainment?")


def test_escalate_node_skips_missing_transaction():
    session = MagicMock()
    session.get.return_value = None

    state = _make_state(confidence=0.65)
    state["escalation_question"] = "What is this?"

    with patch("ledger_agent.agent.nodes.interrupt") as mock_interrupt:
        escalate_node(state, session)
        mock_interrupt.assert_not_called()
        session.commit.assert_not_called()
