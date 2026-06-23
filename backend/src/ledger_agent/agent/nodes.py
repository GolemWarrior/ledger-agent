import logging
from datetime import UTC, datetime
from typing import Literal, Optional, TypedDict

from anthropic import Anthropic
from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ledger_agent.db.models import Category, Resolution, Transaction, TransactionStatus, VendorMemory
from ledger_agent.agent.tools import lookup_vendor_memory
from ledger_agent.agent.prompts import build_classification_prompt, get_live_categories, parse_llm_response

logger = logging.getLogger(__name__)


class ClassificationState(TypedDict):
    transaction_id: int
    description: str
    merchant_name: Optional[str]
    amount_str: str
    date_str: str
    account_name: str
    vendor_memory_hit: Optional[dict]
    category_name: Optional[str]
    confidence: Optional[float]
    reasoning_trace: Optional[str]
    escalation_question: Optional[str]  # Story 2.2 will populate this


def lookup_node(state: ClassificationState, session: Session) -> dict:
    vendor = state.get("merchant_name") or state["description"][:50]
    hit = lookup_vendor_memory(session, vendor)
    if hit:
        return {
            "vendor_memory_hit": {
                "vendor": hit.vendor,
                "category": hit.category.name,
                "hit_count": hit.hit_count,
            },
            "category_name": hit.category.name,
            "confidence": 0.95,
            "reasoning_trace": (
                f"Vendor Memory hit: {vendor} → {hit.category.name} "
                f"(seen {hit.hit_count} time(s))"
            ),
        }
    return {"vendor_memory_hit": None}


def vm_gate(state: ClassificationState) -> Literal["auto_resolve", "classify"]:
    if state.get("vendor_memory_hit") is not None:
        return "auto_resolve"
    return "classify"


def classify_node(state: ClassificationState, session: Session, settings) -> dict:
    categories = get_live_categories(session)
    prompt = build_classification_prompt(state, categories, state.get("vendor_memory_hit"))

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    parsed = parse_llm_response(response.content[0].text)

    vm_note = ""
    if state.get("vendor_memory_hit"):
        vm_note = f" (Vendor Memory hit: {state['vendor_memory_hit']['category']})"
    reasoning = parsed["reasoning"] + vm_note

    return {
        "category_name": parsed["category"],
        "confidence": parsed["confidence"],
        "reasoning_trace": reasoning,
        "escalation_question": parsed.get("question"),
    }


def gate(state: ClassificationState) -> Literal["auto_resolve", "escalate"]:
    if (state.get("confidence") or 0.0) >= 0.80:
        return "auto_resolve"
    return "escalate"


def _upsert_vendor_memory(session: Session, vendor: str, category: Category) -> None:
    """Upsert VendorMemory: create new entry or increment hit_count on existing. Caller commits."""
    vm = session.scalar(select(VendorMemory).where(VendorMemory.vendor == vendor))
    if vm is None:
        session.add(VendorMemory(
            vendor=vendor,
            category_id=category.id,
            hit_count=1,
            last_used_at=datetime.now(UTC),
        ))
    else:
        vm.category_id = category.id
        vm.hit_count = vm.hit_count + 1
        vm.last_used_at = datetime.now(UTC)


def escalate_node(state: ClassificationState, session: Session) -> dict:
    txn = session.get(Transaction, state["transaction_id"])
    if txn is None:
        logger.error("Transaction %s not found — skipping escalate", state["transaction_id"])
        return {}

    txn.status = TransactionStatus.escalated
    txn.escalation_question = (
        state.get("escalation_question") or "What category does this transaction belong to?"
    )
    session.commit()

    # Pause graph — returns user_answer on resume via Command(resume=answer)
    user_answer = interrupt(txn.escalation_question)

    # --- Resume path (DB-only, no LLM calls) ---
    vendor = state.get("merchant_name") or state["description"][:50]

    category = session.scalar(
        select(Category).where(Category.name.ilike(user_answer.strip()))
    )
    if category is None:
        logger.warning(
            "Resolution for txn %s: answer %r has no category match — using Uncategorized",
            state["transaction_id"], user_answer,
        )
        category = session.scalar(select(Category).where(Category.name == "Uncategorized"))
    if category is None:
        logger.error(
            "Transaction %s — Uncategorized not found in DB; cannot resolve", state["transaction_id"]
        )
        return {}

    txn.status = TransactionStatus.resolved
    txn.category_id = category.id
    session.add(Resolution(transaction_id=txn.id, user_answer=user_answer))
    _upsert_vendor_memory(session, vendor, category)
    session.commit()
    return {}


def auto_resolve_node(state: ClassificationState, session: Session) -> dict:
    category = session.scalar(
        select(Category).where(Category.name == state["category_name"])
    )
    if category is None:
        logger.warning(
            "Category '%s' not found for transaction %s — falling back to Uncategorized",
            state["category_name"], state["transaction_id"]
        )
        category = session.scalar(
            select(Category).where(Category.name == "Uncategorized")
        )

    if category is None:
        logger.error(
            "Transaction %s — neither '%s' nor 'Uncategorized' found in DB; skipping auto-resolve",
            state["transaction_id"], state["category_name"]
        )
        return {}

    txn = session.get(Transaction, state["transaction_id"])
    if txn is None:
        logger.error("Transaction %s not found — skipping auto-resolve", state["transaction_id"])
        return {}

    txn.status = TransactionStatus.resolved
    txn.category_id = category.id
    txn.confidence_score = state["confidence"]
    txn.reasoning_trace = state["reasoning_trace"]

    # Upsert vendor memory (FR-21 — deferred from Story 2.1)
    vendor = state.get("merchant_name") or state["description"][:50]
    _upsert_vendor_memory(session, vendor, category)

    session.commit()
    return {}
