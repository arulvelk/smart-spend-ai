"""Batch transaction categorization with Gemini structured output."""
from __future__ import annotations

import json

from pydantic import BaseModel, Field

from .categories import CATEGORIES, Category
from .llm import LLM
from .warehouse import CategoryUpdate, Warehouse

BATCH_SIZE = 40  # many transactions per call keeps Gemini cost to fractions of a cent

PROMPT = """You categorize bank and credit-card transactions for a personal budgeting app.

For each transaction, return:
- merchant_name: the clean, human-readable merchant (e.g. "SQ *BLUE BOTTLE CO 0423" -> "Blue Bottle Coffee", "AMZN Mktp US*2K4L7" -> "Amazon").
- category: exactly one of {categories}.
- confidence: 0.0-1.0, how sure you are of the category.

Rules:
- Payment processors (SQ *, TST*, DD *, DOORDASH*, UBER *EATS) name the real merchant after the prefix; categorize that merchant.
- UBER *TRIP and LYFT are Transportation; UBER *EATS and DoorDash are Dining.
- Coffee shops are Coffee, not Dining.
- Rent and mortgage are Housing. Payroll and direct deposits (credits) are Income.
- Credit card autopay, Venmo, Zelle and transfers between accounts are Transfer.
- Streaming, music, cloud storage and app subscriptions are Subscriptions; gym memberships are Fitness.
- ATM and bank fees are Fees.
Return one result per input transaction_id, in the same order.

Transactions (JSON):
{rows}
"""


class CategorizedTxn(BaseModel):
    transaction_id: str
    merchant_name: str
    category: Category
    confidence: float = Field(ge=0, le=1)


class CategorizedBatch(BaseModel):
    results: list[CategorizedTxn]


def categorize_rows(llm: LLM, rows: list[dict]) -> list[CategoryUpdate]:
    """Categorize transaction dicts (transaction_id, raw_description, amount, direction, channel)."""
    updates: list[CategoryUpdate] = []
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        valid_ids = {r["transaction_id"] for r in batch}
        prompt = PROMPT.format(categories=", ".join(CATEGORIES), rows=json.dumps(batch, default=str))
        out = llm.structured(prompt, CategorizedBatch)
        for r in out.results:
            if r.transaction_id in valid_ids:  # ignore anything the model invented
                updates.append(CategoryUpdate(r.transaction_id, r.merchant_name, r.category.value, r.confidence))
    return updates


def categorize_pending(llm: LLM, wh: Warehouse, limit: int = 200) -> dict:
    rows = wh.uncategorized(limit)
    updates = categorize_rows(llm, rows)
    updated = wh.apply_categories(updates)
    low = [u for u in updates if u.confidence < 0.6]
    return {
        "pending": len(rows),
        "categorized": updated,
        "low_confidence": [{"transaction_id": u.transaction_id, "merchant": u.merchant_name, "category": u.category,
                            "confidence": u.confidence} for u in low],
    }
