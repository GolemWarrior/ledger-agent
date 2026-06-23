from unittest.mock import MagicMock, patch

from ledger_agent.agent.nodes import ClassificationState, auto_resolve_node, classify_node, escalate_node, gate, lookup_node, vm_gate
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
    assert result["category_name"] == "Groceries"
    assert result["confidence"] == 0.95
    assert "Vendor Memory hit" in result["reasoning_trace"]
    assert "Groceries" in result["reasoning_trace"]


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


def test_lookup_node_with_hit_sets_fast_path_fields():
    """VM hit → category_name, confidence, reasoning_trace set for auto-resolve short-circuit."""
    hit = _make_vm_hit(category_name="Groceries", hit_count=5)
    session = MagicMock()
    session.scalar.return_value = hit
    state = _make_state(merchant_name="Whole Foods")

    result = lookup_node(state, session)

    assert result["category_name"] == "Groceries"
    assert result["confidence"] == 0.95
    assert "Vendor Memory hit" in result["reasoning_trace"]
    assert "Groceries" in result["reasoning_trace"]
    assert "5" in result["reasoning_trace"]


def test_lookup_node_with_hit_preserves_vm_hit_dict():
    """VM hit dict is still returned alongside fast-path fields (classify_node uses it)."""
    hit = _make_vm_hit()
    session = MagicMock()
    session.scalar.return_value = hit
    state = _make_state(merchant_name="Whole Foods")

    result = lookup_node(state, session)

    assert result["vendor_memory_hit"]["category"] == "Groceries"
    assert result["vendor_memory_hit"]["hit_count"] == 3
    assert result["vendor_memory_hit"]["vendor"] == "WHOLE FOODS MARKET"


def test_lookup_node_no_hit_returns_only_none():
    """No VM hit → only vendor_memory_hit=None; no fast-path keys in result."""
    session = MagicMock()
    session.scalar.return_value = None
    state = _make_state(merchant_name="Unknown Store")

    result = lookup_node(state, session)

    assert result == {"vendor_memory_hit": None}
    assert "category_name" not in result
    assert "confidence" not in result
    assert "reasoning_trace" not in result


def test_vm_gate_returns_auto_resolve_on_hit():
    """vm_gate routes to auto_resolve when vendor_memory_hit is set."""
    state = _make_state()
    state["vendor_memory_hit"] = {"vendor": "Target", "category": "Groceries", "hit_count": 2}

    assert vm_gate(state) == "auto_resolve"


def test_vm_gate_returns_classify_on_no_hit():
    """vm_gate routes to classify when vendor_memory_hit is None."""
    state = _make_state()
    state["vendor_memory_hit"] = None

    assert vm_gate(state) == "classify"


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
    session.scalar.side_effect = [category, None]  # [category found, no existing VM]
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
    session.scalar.side_effect = [None, uncategorized, None]  # [no match, Uncategorized, no existing VM]
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
    txn.id = 1
    category = _make_category(cat_id=5, name="Groceries")
    session = MagicMock()
    session.get.return_value = txn
    session.scalar.side_effect = [category, None]  # category match; no existing VM

    state = _make_state(confidence=0.65)
    state["escalation_question"] = "Is this a business or personal expense?"

    # Capture txn.status at the point of the first commit (pre-interrupt).
    status_at_first_commit = []
    original_commit = session.commit.side_effect

    def _record_commit():
        status_at_first_commit.append(txn.status)
        if original_commit:
            original_commit()

    session.commit.side_effect = _record_commit

    with patch("ledger_agent.agent.nodes.interrupt", return_value="Groceries") as mock_interrupt:
        escalate_node(state, session)

    assert status_at_first_commit[0] == TransactionStatus.escalated
    assert txn.escalation_question == "Is this a business or personal expense?"
    mock_interrupt.assert_called_once_with("Is this a business or personal expense?")
    session.commit.assert_called()


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


# --- escalate_node resume path tests ---

def test_escalate_node_resume_updates_transaction_resolved():
    """After resume: txn.status = resolved, txn.category_id set."""
    txn = MagicMock()
    txn.id = 1
    category = _make_category(cat_id=7, name="Dining")
    session = MagicMock()
    session.get.return_value = txn
    session.scalar.side_effect = [category, None]  # ilike match; no existing VM

    state = _make_state(confidence=0.65, merchant_name="Chipotle")
    state["escalation_question"] = "Is this Dining or Entertainment?"

    with patch("ledger_agent.agent.nodes.interrupt", return_value="Dining"):
        escalate_node(state, session)

    assert txn.status == TransactionStatus.resolved
    assert txn.category_id == 7
    session.commit.assert_called()


def test_escalate_node_resume_writes_resolution_record():
    """After resume: Resolution record written to session."""
    from ledger_agent.db.models import Resolution
    txn = MagicMock()
    txn.id = 42
    category = _make_category(name="Dining")
    session = MagicMock()
    session.get.return_value = txn
    session.scalar.side_effect = [category, None]

    state = _make_state(confidence=0.65, merchant_name="Chipotle")
    state["escalation_question"] = "Is this Dining?"

    with patch("ledger_agent.agent.nodes.interrupt", return_value="Dining"):
        escalate_node(state, session)

    added = [call[0][0] for call in session.add.call_args_list]
    resolution = next((a for a in added if isinstance(a, Resolution)), None)
    assert resolution is not None
    assert resolution.transaction_id == 42
    assert resolution.user_answer == "Dining"


def test_escalate_node_resume_upserts_vendor_memory():
    """After resume: VendorMemory upserted when no existing entry."""
    from ledger_agent.db.models import VendorMemory
    txn = MagicMock()
    txn.id = 1
    category = _make_category(name="Dining")
    session = MagicMock()
    session.get.return_value = txn
    session.scalar.side_effect = [category, None]  # [category match, no existing VM]

    state = _make_state(confidence=0.65, merchant_name="Chipotle")
    state["escalation_question"] = "Is this Dining?"

    with patch("ledger_agent.agent.nodes.interrupt", return_value="Dining"):
        escalate_node(state, session)

    added = [call[0][0] for call in session.add.call_args_list]
    vm_added = [a for a in added if isinstance(a, VendorMemory)]
    assert len(vm_added) == 1
    assert vm_added[0].vendor == "Chipotle"
    assert vm_added[0].hit_count == 1


def test_escalate_node_resume_fallback_to_uncategorized():
    """If answer doesn't match any category, falls back to Uncategorized."""
    txn = MagicMock()
    txn.id = 1
    uncategorized = _make_category(cat_id=10, name="Uncategorized")
    session = MagicMock()
    session.get.return_value = txn
    session.scalar.side_effect = [None, uncategorized, None]

    state = _make_state(confidence=0.65)
    state["escalation_question"] = "What is this?"

    with patch("ledger_agent.agent.nodes.interrupt", return_value="some random text"):
        escalate_node(state, session)

    assert txn.category_id == 10
    assert txn.status == TransactionStatus.resolved
    session.commit.assert_called()


# --- auto_resolve_node VM upsert tests ---

def test_auto_resolve_node_upserts_new_vendor_memory():
    """No existing VM entry → new VendorMemory created with hit_count=1."""
    from ledger_agent.db.models import VendorMemory
    category = _make_category(cat_id=5, name="Groceries")
    txn = MagicMock()
    txn.id = 1
    session = MagicMock()
    session.scalar.side_effect = [category, None]  # [category found, no existing VM]
    session.get.return_value = txn

    state = _make_state(confidence=0.92, merchant_name="Whole Foods")
    state["reasoning_trace"] = "Supermarket"
    auto_resolve_node(state, session)

    added = [call[0][0] for call in session.add.call_args_list]
    vm_added = [a for a in added if isinstance(a, VendorMemory)]
    assert len(vm_added) == 1
    assert vm_added[0].vendor == "Whole Foods"
    assert vm_added[0].hit_count == 1
    assert vm_added[0].category_id == 5


def test_auto_resolve_node_increments_existing_vendor_memory():
    """Existing VM entry → hit_count incremented and category_id updated."""
    category = _make_category(cat_id=5, name="Groceries")
    existing_vm = MagicMock()
    existing_vm.hit_count = 3
    txn = MagicMock()
    txn.id = 1
    session = MagicMock()
    session.scalar.side_effect = [category, existing_vm]  # [category found, existing VM]
    session.get.return_value = txn

    state = _make_state(confidence=0.92, merchant_name="Whole Foods")
    state["reasoning_trace"] = "Supermarket"
    auto_resolve_node(state, session)

    assert existing_vm.hit_count == 4
    assert existing_vm.category_id == 5
    session.commit.assert_called_once()
