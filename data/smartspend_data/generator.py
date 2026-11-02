"""Deterministic synthetic transaction generator.

Every day is generated from its own seeded RNG, so `generate_day(d)` always
returns the same rows (same ids) for the same date and seed. The backfill and
the daily Cloud Function share this code, and the daily job can MERGE on
transaction_id without creating duplicates.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

from . import catalog
from .catalog import Merchant

USER_ID = "demo-user"
TAX_RATE = 0.1025  # Oakland sales tax


@dataclass
class Txn:
    transaction_id: str
    user_id: str
    account_id: str
    txn_date: date
    posted_at: datetime
    raw_description: str
    amount: float
    direction: str
    currency: str
    channel: str
    source: str
    true_merchant: str
    true_category: str
    receipt: dict | None = field(default=None, repr=False)

    def bq_row(self, *, categorized: bool, ingested_at: datetime) -> dict:
        """Row for the `transactions` table. Category fields are blank unless
        `categorized`, which lets the agent categorize recent rows itself."""
        return {
            "transaction_id": self.transaction_id,
            "user_id": self.user_id,
            "account_id": self.account_id,
            "txn_date": self.txn_date.isoformat(),
            "posted_at": self.posted_at.isoformat(),
            "raw_description": self.raw_description,
            "merchant_name": self.true_merchant if categorized else None,
            "amount": f"{self.amount:.2f}",
            "direction": self.direction,
            "currency": self.currency,
            "channel": self.channel,
            "category": self.true_category if categorized else None,
            "category_source": "seed" if categorized else None,
            "category_confidence": 1.0 if categorized else None,
            "source": self.source,
            "ingested_at": ingested_at.isoformat(),
            "import_id": None,
        }

    def label_row(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "true_merchant": self.true_merchant,
            "true_category": self.true_category,
        }


def _poisson(rng: random.Random, lam: float) -> int:
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def _descriptor(rng: random.Random, m: Merchant) -> str:
    text = rng.choice(m.descriptors).format(n=rng.randint(100, 99999), city=rng.choice(catalog.CITIES))
    if rng.random() < 0.15:
        text = text.replace(" ", "  ", 1)  # double spaces happen in real feeds
    return text[:40]


def _money(x: float) -> float:
    return round(x + 1e-9, 2)


def _receipt(rng: random.Random, m: Merchant, d: date, when: datetime) -> dict:
    """Build line items; the transaction amount is the receipt total, so the two always reconcile."""
    n_items = rng.randint(2, 4) if m.tip else rng.randint(3, 12)
    lines = []
    for desc, lo, hi in rng.sample(list(m.items), k=min(n_items, len(m.items))):
        qty = 1 if m.tip or rng.random() < 0.75 else rng.randint(2, 3)
        unit = _money(rng.uniform(lo, hi))
        lines.append({"description": desc, "quantity": qty, "unit_price": unit, "amount": _money(unit * qty)})
    subtotal = _money(sum(li["amount"] for li in lines))
    tax = _money(subtotal * TAX_RATE)
    tip = _money(subtotal * rng.choice([0.15, 0.18, 0.20])) if m.tip else 0.0
    return {
        "merchant_name": m.name,
        "address": catalog.MERCHANT_ADDRESSES.get(m.name, ""),
        "receipt_date": d.isoformat(),
        "receipt_time": when.strftime("%H:%M"),
        "line_items": lines,
        "subtotal": subtotal,
        "tax": tax,
        "tip": tip,
        "total": _money(subtotal + tax + tip),
        "card_last4": "4417",
        "category": m.category,
    }


def _txn_id(seed: int, d: date, idx: int) -> str:
    return "txn_" + hashlib.sha1(f"{seed}|{d.isoformat()}|{idx}".encode()).hexdigest()[:16]


def _rate_multiplier(m: Merchant, d: date, end: date) -> float:
    mult = 1.0
    wd = d.weekday()
    if m.category == "Coffee":
        mult *= 1.3 if wd < 5 else 0.5
    if m.category == "Dining":
        mult *= 1.4 if wd >= 4 else 0.85
        # Deliberate overspend in the most recent month, so budget alerts have something to say.
        if (end - d).days < 30:
            mult *= 2.2
    if m.category == "Shopping" and d.month in (11, 12):
        mult *= 2.2  # holiday season
    if m.category == "Groceries" and wd == 6:
        mult *= 1.8
    return mult


def generate_day(d: date, *, seed: int = 42, end: date | None = None, source: str = "daily_feed") -> list[Txn]:
    """All transactions for one calendar day."""
    end = end or d
    rng = random.Random(f"{seed}|{d.isoformat()}")
    events: list[tuple[Merchant, float | None]] = []

    for m, dom in catalog.RECURRING:
        if d.day == dom:
            events.append((m, None))
    new_sub, new_dom = catalog.NEW_SUBSCRIPTION
    if d.day == new_dom and (end - d).days < 75:
        events.append((new_sub, None))
    # Biweekly Friday payroll, anchored to a fixed Friday.
    if d.weekday() == 4 and ((d - date(2024, 1, 5)).days // 7) % 2 == 0:
        events.append((catalog.PAYROLL, None))

    for m, base_rate in catalog.FREQUENT:
        for _ in range(_poisson(rng, base_rate * _rate_multiplier(m, d, end))):
            events.append((m, None))

    if d.month in catalog.TRAVEL_MONTHS and d.day in (10, 11, 12):
        m = catalog.TRAVEL[d.day - 10]
        events.append((m, None))

    txns: list[Txn] = []
    for idx, (m, _) in enumerate(events):
        hour = rng.randint(7, 22) if m.channel == "card" else 3
        when = datetime.combine(d, time(hour, rng.randint(0, 59)), tzinfo=timezone.utc)
        receipt = _receipt(rng, m, d, when) if m.items else None
        if receipt:
            amount = receipt["total"]
        else:
            lo, hi = m.amount
            amount = _money(rng.uniform(lo, hi)) if lo != hi else lo
        direction = "credit" if m.category == "Income" else "debit"
        txns.append(Txn(
            transaction_id=_txn_id(seed, d, idx),
            user_id=USER_ID,
            account_id=m.account,
            txn_date=d,
            posted_at=when + timedelta(days=1 if m.channel == "card" else 0),
            raw_description=_descriptor(rng, m),
            amount=amount,
            direction=direction,
            currency="USD",
            channel=m.channel,
            source=source,
            true_merchant=m.name,
            true_category=m.category,
            receipt=receipt,
        ))
    return txns


def generate_range(start: date, end: date, *, seed: int = 42, source: str = "backfill") -> Iterable[Txn]:
    d = start
    while d <= end:
        yield from generate_day(d, seed=seed, end=end, source=source)
        d += timedelta(days=1)


DEMO_ACCOUNTS = [
    {"account_id": "chk-001", "name": "Demo Everyday Checking", "type": "checking", "institution": "Demo Bank", "last4": "0021"},
    {"account_id": "cc-001", "name": "Demo Rewards Visa", "type": "credit_card", "institution": "Demo Bank", "last4": "4417"},
]


def account_rows(created_at: datetime) -> list[dict]:
    """The two synthetic accounts the backfill and the daily job write to."""
    return [{**a, "user_id": USER_ID, "is_demo": True, "created_at": created_at.isoformat()} for a in DEMO_ACCOUNTS]


def budget_rows(effective_from: date, budgets: dict[str, float] | None = None) -> list[dict]:
    budgets = budgets or catalog.DEFAULT_BUDGETS
    return [
        {"user_id": USER_ID, "category": c, "monthly_limit": f"{v:.2f}", "effective_from": effective_from.isoformat()}
        for c, v in budgets.items()
    ]
