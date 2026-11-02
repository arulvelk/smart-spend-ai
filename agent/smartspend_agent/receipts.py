"""Receipt understanding with Gemini multimodal + matching to a bank transaction."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from .categories import CATEGORIES, Category
from .llm import LLM
from .warehouse import Warehouse, now_utc

PROMPT = f"""Extract the purchase from this receipt photo.
Return the merchant name as printed, the purchase date (YYYY-MM-DD), every line item, subtotal, tax, tip (0 if none) and total.
Use numbers without currency symbols. If a value is unreadable, use null.
Also choose the spending category, one of: {", ".join(CATEGORIES)}.
Set confidence (0-1) to how legible and internally consistent the receipt is (line items add up to subtotal, subtotal + tax + tip = total)."""


class LineItem(BaseModel):
    description: str
    quantity: float = 1
    unit_price: Optional[float] = None
    amount: float


class ReceiptParse(BaseModel):
    merchant_name: str
    receipt_date: Optional[date] = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    tip: Optional[float] = 0
    total: float
    category: Category
    confidence: float = Field(ge=0, le=1)

    def arithmetic_ok(self) -> bool:
        """Independent check of the model's extraction, so we never trust it blindly."""
        if self.subtotal is None:
            return False
        items_ok = abs(sum(li.amount for li in self.line_items) - self.subtotal) <= 0.02
        total_ok = abs(self.subtotal + (self.tax or 0) + (self.tip or 0) - self.total) <= 0.02
        return items_ok and total_ok


def parse_receipt(llm: LLM, image: bytes, mime_type: str = "image/jpeg") -> ReceiptParse:
    return llm.structured(PROMPT, ReceiptParse, image=image, mime_type=mime_type)


def process_receipt(llm: LLM, wh: Warehouse, *, image: bytes, mime_type: str, gcs_uri: str,
                    user_id: str, model_name: str) -> dict:
    parsed = parse_receipt(llm, image, mime_type)
    match = None
    if parsed.receipt_date:
        match = wh.find_transaction_for_receipt(parsed.total, parsed.receipt_date)
        if match:
            wh.tag_transaction(match["transaction_id"], parsed.merchant_name, parsed.category.value)

    receipt_id = "rcpt_" + uuid.uuid4().hex[:16]
    wh.insert_receipt({
        "receipt_id": receipt_id,
        "user_id": user_id,
        "gcs_uri": gcs_uri,
        "uploaded_at": now_utc(),
        "merchant_name": parsed.merchant_name,
        "receipt_date": parsed.receipt_date.isoformat() if parsed.receipt_date else None,
        "subtotal": parsed.subtotal,
        "tax": parsed.tax,
        "tip": parsed.tip,
        "total": parsed.total,
        "line_items": [li.model_dump() for li in parsed.line_items],
        "category": parsed.category.value,
        "parse_model": model_name,
        "parse_confidence": parsed.confidence,
        "matched_transaction_id": match["transaction_id"] if match else None,
    })
    return {
        "receipt_id": receipt_id,
        "parsed": parsed.model_dump(mode="json"),
        "arithmetic_ok": parsed.arithmetic_ok(),
        "matched_transaction": match,
        "gcs_uri": gcs_uri,
    }
