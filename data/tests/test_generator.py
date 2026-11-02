import json
from datetime import date, datetime, timezone
from pathlib import Path

from smartspend_data import budget_rows, generate_day, generate_range
from smartspend_data.catalog import CATEGORIES

SCHEMAS = Path(__file__).resolve().parents[2] / "infra" / "terraform" / "schemas"
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _fields(table):
    return {f["name"]: f for f in json.loads((SCHEMAS / f"{table}.json").read_text())}


def test_generate_day_is_deterministic():
    d = date(2026, 10, 3)
    a = [t.transaction_id for t in generate_day(d)]
    b = [t.transaction_id for t in generate_day(d)]
    assert a == b and len(set(a)) == len(a)


def test_ids_unique_across_year():
    ids = [t.transaction_id for t in generate_range(date(2025, 11, 1), date(2026, 10, 31))]
    assert len(ids) == len(set(ids)) > 500


def test_rows_match_bigquery_schema():
    fields = _fields("transactions")
    for t in generate_range(date(2026, 9, 1), date(2026, 9, 30)):
        for categorized in (True, False):
            row = t.bq_row(categorized=categorized, ingested_at=NOW)
            assert set(row) == set(fields)
            for name, f in fields.items():
                if f["mode"] == "REQUIRED":
                    assert row[name] is not None, name
    assert set(budget_rows(date(2026, 1, 1))[0]) == set(_fields("budgets"))


def test_categories_are_known_and_receipts_reconcile():
    for t in generate_range(date(2026, 8, 1), date(2026, 8, 31)):
        assert t.true_category in CATEGORIES
        assert t.amount > 0
        if t.receipt:
            r = t.receipt
            assert abs(sum(li["amount"] for li in r["line_items"]) - r["subtotal"]) < 0.011
            assert abs(r["subtotal"] + r["tax"] + r["tip"] - r["total"]) < 0.011
            assert r["total"] == t.amount


def test_payroll_is_biweekly():
    pay = [t.txn_date for t in generate_range(date(2026, 1, 1), date(2026, 3, 31)) if t.true_category == "Income"]
    assert all((b - a).days == 14 for a, b in zip(pay, pay[1:]))
