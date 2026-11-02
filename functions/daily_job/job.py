"""Daily SmartSpend job: ingest the bank feed, categorize, raise budget alerts.

Pure planning logic (which days to ingest, which alerts to raise) is separated
from the GCP calls so it can be unit-tested without credentials.
"""
from __future__ import annotations

import calendar
import hashlib
from dataclasses import dataclass
from datetime import date, timedelta

MAX_CATCHUP_DAYS = 31


def days_to_ingest(last_loaded: date | None, through: date) -> list[date]:
    """Every day after the last loaded one, up to and including `through` (capped)."""
    if last_loaded is None:
        start = through
    else:
        start = last_loaded + timedelta(days=1)
    start = max(start, through - timedelta(days=MAX_CATCHUP_DAYS - 1))
    return [start + timedelta(days=i) for i in range((through - start).days + 1)]


@dataclass(frozen=True)
class Alert:
    alert_type: str  # budget_exceeded | budget_threshold | on_pace_to_exceed
    category: str
    amount_spent: float
    monthly_limit: float
    message: str

    def row(self, user_id: str, period_month: date, created_at: str) -> dict:
        key = f"{user_id}|{period_month}|{self.category}|{self.alert_type}"
        return {
            "alert_id": "alrt_" + hashlib.sha1(key.encode()).hexdigest()[:16],
            "user_id": user_id,
            "alert_type": self.alert_type,
            "category": self.category,
            "period_month": period_month.isoformat(),
            "amount_spent": round(self.amount_spent, 2),
            "monthly_limit": round(self.monthly_limit, 2),
            "message": self.message,
            "created_at": created_at,
        }


def plan_alerts(budgets: list[dict], today: date, already_sent: set[tuple[str, str]],
                threshold: float = 0.8, pace_margin: float = 1.1, min_pace_day: int = 5) -> list[Alert]:
    """Decide which alerts to raise for the current month.

    budgets: rows with category, monthly_limit, spend_month_to_date.
    already_sent: {(category, alert_type)} already raised this month, so each alert fires once.
    Pace alerts compare a straight-line projection with the limit, so they are useful
    early in the month, before any absolute threshold is crossed.
    """
    dim = calendar.monthrange(today.year, today.month)[1]
    alerts: list[Alert] = []
    for b in budgets:
        cat, limit, spent = b["category"], float(b["monthly_limit"]), float(b["spend_month_to_date"] or 0)
        if limit <= 0:
            continue
        pct = spent / limit
        projected = spent / today.day * dim
        if pct >= 1:
            a = Alert("budget_exceeded", cat, spent, limit,
                      f"{cat} is over budget: ${spent:,.2f} spent, {pct:.0%} of the ${limit:,.0f} monthly limit.")
        elif pct >= threshold:
            a = Alert("budget_threshold", cat, spent, limit,
                      f"{cat} has used {pct:.0%} of its ${limit:,.0f} budget with {dim - today.day} days left.")
        elif today.day >= min_pace_day and projected > limit * pace_margin:
            a = Alert("on_pace_to_exceed", cat, spent, limit,
                      f"{cat} is on pace for ${projected:,.0f} this month, {projected / limit:.1f}x its ${limit:,.0f} budget.")
        else:
            continue
        if (cat, a.alert_type) not in already_sent:
            alerts.append(a)
    return alerts
