import json
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledger_agent.db.models import Category

logger = logging.getLogger(__name__)


def get_live_categories(session: Session) -> list[dict]:
    """Query categories fresh from DB. Never cache — must reflect adds/renames/deletes immediately."""
    cats = list(session.scalars(select(Category)))
    return [{"name": c.name, "hint": c.hint} for c in cats]


def build_classification_prompt(
    state: dict,
    categories: list[dict],
    vendor_memory_hit: Optional[dict] = None,
) -> str:
    lines = [
        "Classify this financial transaction into exactly one of the categories listed below.",
        "",
        f"Description: {state['description']}",
    ]
    if state.get("merchant_name"):
        lines.append(f"Merchant: {state['merchant_name']}")
    lines += [
        f"Amount: ${state['amount_str']}",
        f"Date: {state['date_str']}",
        f"Account: {state['account_name']}",
        "",
    ]
    if vendor_memory_hit:
        lines += [
            f"Prior classification: This vendor was previously classified as "
            f"'{vendor_memory_hit['category']}' "
            f"({vendor_memory_hit['hit_count']} time(s)). Use this as a strong signal.",
            "",
        ]
    lines.append("Categories:")
    for cat in categories:
        hint_part = f" — {cat['hint']}" if cat.get("hint") else ""
        lines.append(f"  {cat['name']}{hint_part}")
    lines += [
        "",
        "Respond with valid JSON only (no markdown fences, no extra text):",
        '{"category": "<exact category name>", "confidence": <0.0-1.0>, "reasoning": "<1-2 sentences>", "question": "<specific question or omit if confident>"}',
        "",
        "Rules:",
        "  - category must exactly match one of the names above",
        "  - confidence 1.0 = certain, 0.0 = no idea",
        "  - use confidence < 0.80 when genuinely unsure which category fits",
        '  - if confidence < 0.80, add a "question" field: one specific, answerable question',
        "    about this transaction (not \"what category is this?\") that would help you decide;",
        '    e.g. "Is this an Amazon order for household goods or a business expense?"',
    ]
    return "\n".join(lines)


def parse_llm_response(text: str) -> dict:
    """Parse JSON from LLM response. Returns dict with category, confidence, reasoning."""
    text = text.strip()
    # Strip markdown fences if present (defensive)
    if text.startswith("```"):
        text = "\n".join(
            line for line in text.splitlines()
            if not line.startswith("```")
        ).strip()
    parsed = json.loads(text)
    if "category" not in parsed or "confidence" not in parsed:
        raise ValueError(f"LLM response missing required keys: {list(parsed.keys())}")
    confidence = float(parsed["confidence"])
    confidence = max(0.0, min(1.0, confidence))
    return {
        "category": str(parsed["category"]),
        "confidence": confidence,
        "reasoning": str(parsed.get("reasoning", "")),
        "question": str(parsed["question"]) if parsed.get("question") else None,
    }
