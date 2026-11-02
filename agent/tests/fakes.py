"""In-memory fakes so agent and API tests run with no GCP access."""
from __future__ import annotations

import json
import re
from datetime import date

from smartspend_agent.categorizer import CategorizedBatch, CategorizedTxn
from smartspend_agent.graph import Intent
from smartspend_agent.receipts import ReceiptParse


class FakeLLM:
    def __init__(self, intent: dict | None = None, receipt: dict | None = None, answer: str = "You spent $123.45."):
        self.intent = intent or {"intent": "spend_summary", "period": "this_month"}
        self.receipt = receipt
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    def structured(self, prompt, schema, *, image=None, mime_type="image/jpeg"):
        self.calls.append((schema.__name__, prompt))
        if schema is Intent:
            return Intent.model_validate(self.intent)
        if schema is CategorizedBatch:
            rows = json.loads(prompt[prompt.index("Transactions (JSON):") + len("Transactions (JSON):"):])
            results = [CategorizedTxn(transaction_id=r["transaction_id"], merchant_name=r["raw_description"].title(),
                                      category="Coffee" if "COFFEE" in r["raw_description"] else "Shopping",
                                      confidence=0.9) for r in rows]
            results.append(CategorizedTxn(transaction_id="txn_invented", merchant_name="X", category="Fees", confidence=1))
            return CategorizedBatch(results=results)
        if schema is ReceiptParse:
            return ReceiptParse.model_validate(self.receipt)
        raise AssertionError(schema)

    def text(self, prompt, *, system=None):
        self.calls.append(("text", prompt))
        return self.answer


class FakeWarehouse:
    def __init__(self):
        self.applied = []
        self.receipts = []
        self.tagged = []
        self.queries: list[tuple] = []
        self.pending = [
            {"transaction_id": "txn_1", "raw_description": "SQ *BLUE BOTTLE COFFEE", "amount": 6.5, "direction": "debit", "channel": "card"},
            {"transaction_id": "txn_2", "raw_description": "AMZN Mktp US*2K4L7", "amount": 42.0, "direction": "debit", "channel": "card"},
        ]

    def _log(self, *a):
        self.queries.append(a)

    def spend_by_category(self, start, end):
        self._log("spend_by_category", start, end)
        return [{"category": "Dining", "spend": 812.4, "txns": 31}, {"category": "Groceries", "spend": 640.1, "txns": 12}]

    def monthly_trend(self, start, end, category=None):
        self._log("monthly_trend", start, end, category)
        return [{"month": "2026-10-01", "spend": 500.0}, {"month": "2026-11-01", "spend": 812.4}]

    def top_merchants(self, start, end, category=None, limit=5):
        self._log("top_merchants", start, end, category, limit)
        return [{"merchant": "Tacos El Gordo", "spend": 210.0, "txns": 5}]

    def merchant_spend(self, merchant, start, end):
        self._log("merchant_spend", merchant, start, end)
        return [{"merchant": "Starbucks", "spend": 64.2, "txns": 11}]

    def budget_status(self):
        self._log("budget_status")
        return [{"category": "Dining", "monthly_limit": 450.0, "spend_month_to_date": 812.4, "pct_used": 180.5}]

    def transactions(self, start, end, category=None, limit=100):
        self._log("transactions", start, end, category, limit)
        return [{"transaction_id": "txn_1", "txn_date": "2026-11-01", "raw_description": "SQ *BLUE BOTTLE COFFEE", "amount": 6.5}]

    def uncategorized(self, limit):
        return self.pending[:limit]

    def apply_categories(self, updates):
        self.applied.extend(updates)
        return len(updates)

    def categorization_accuracy(self):
        return {"evaluated": 2, "correct": 2, "accuracy_pct": 100.0, "avg_confidence": 0.9, "sample_misses": []}

    def find_transaction_for_receipt(self, total, on, days=3):
        self._log("find_transaction_for_receipt", total, on)
        if abs(total - 43.81) < 0.01 and abs((on - date(2026, 10, 6)).days) <= days:
            return {"transaction_id": "txn_pizza", "txn_date": "2026-10-06", "raw_description": "TST* PIZZERIA DELFINA", "amount": 43.81}
        return None

    def tag_transaction(self, transaction_id, merchant, category):
        self.tagged.append((transaction_id, merchant, category))

    def insert_receipt(self, row):
        self.receipts.append(row)

    def alerts(self, limit=20):
        return [{"alert_id": "a1", "alert_type": "budget_exceeded", "category": "Dining", "message": "Dining is over budget"}]


PIZZA_RECEIPT = {
    "merchant_name": "PIZZERIA DELFINA", "receipt_date": "2026-10-06",
    "line_items": [{"description": "CAESAR SALAD", "amount": 13.58}, {"description": "FRIES", "amount": 6.48},
                   {"description": "CARNITAS BURRITO", "amount": 13.57}],
    "subtotal": 33.63, "tax": 3.45, "tip": 6.73, "total": 43.81, "category": "Dining", "confidence": 0.95,
}
