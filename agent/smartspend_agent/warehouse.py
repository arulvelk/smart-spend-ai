"""BigQuery access for the agent and API.

The LLM never writes SQL. It picks an intent and parameters, and this module
runs fixed, parameterized queries. That keeps answers auditable and makes SQL
injection through the chat box impossible.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

SPEND_FILTER = "direction = 'debit' AND COALESCE(category, '') NOT IN ('Transfer', 'Income')"


def _plain(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


@dataclass(frozen=True)
class CategoryUpdate:
    transaction_id: str
    merchant_name: str
    category: str
    confidence: float


class Warehouse(Protocol):
    def spend_by_category(self, start: date, end: date) -> list[dict]: ...
    def monthly_trend(self, start: date, end: date, category: str | None = None) -> list[dict]: ...
    def top_merchants(self, start: date, end: date, category: str | None = None, limit: int = 5) -> list[dict]: ...
    def merchant_spend(self, merchant: str, start: date, end: date) -> list[dict]: ...
    def budget_status(self) -> list[dict]: ...
    def transactions(self, start: date, end: date, category: str | None = None, limit: int = 100) -> list[dict]: ...
    def uncategorized(self, limit: int) -> list[dict]: ...
    def apply_categories(self, updates: list[CategoryUpdate]) -> int: ...
    def categorization_accuracy(self) -> dict: ...
    def find_transaction_for_receipt(self, total: float, on: date, days: int = 3) -> dict | None: ...
    def insert_receipt(self, row: dict) -> None: ...
    def tag_transaction(self, transaction_id: str, merchant: str, category: str) -> None: ...
    def alerts(self, limit: int = 20) -> list[dict]: ...


class BigQueryWarehouse:
    def __init__(self, project: str, dataset: str, user_id: str, client=None):
        from google.cloud import bigquery

        self._bq = bigquery
        self.client = client or bigquery.Client(project=project)
        self.project, self.dataset = project, dataset
        self.table = lambda name: f"`{project}.{dataset}.{name}`"
        self.user_id = user_id

    # -- helpers ---------------------------------------------------------
    def _q(self, sql: str, **params: Any) -> list[dict]:
        bq = self._bq
        qp = [bq.ScalarQueryParameter("user_id", "STRING", self.user_id)]
        for name, value in params.items():
            if isinstance(value, bq.ArrayQueryParameter):
                qp.append(value)
                continue
            kind = {date: "DATE", int: "INT64", float: "FLOAT64", str: "STRING"}.get(type(value), "STRING")
            qp.append(bq.ScalarQueryParameter(name, kind, value))
        rows = self.client.query(sql, job_config=bq.QueryJobConfig(query_parameters=qp)).result()
        return [{k: _plain(v) for k, v in dict(r).items()} for r in rows]

    # -- analytics -------------------------------------------------------
    def spend_by_category(self, start, end):
        return self._q(
            f"""SELECT COALESCE(category, 'Uncategorized') AS category, ROUND(SUM(amount), 2) AS spend, COUNT(*) AS txns
                FROM {self.table('transactions')}
                WHERE user_id = @user_id AND txn_date BETWEEN @start AND @end AND {SPEND_FILTER}
                GROUP BY category ORDER BY spend DESC""",
            start=start, end=end,
        )

    def monthly_trend(self, start, end, category=None):
        return self._q(
            f"""SELECT DATE_TRUNC(txn_date, MONTH) AS month, ROUND(SUM(amount), 2) AS spend
                FROM {self.table('transactions')}
                WHERE user_id = @user_id AND txn_date BETWEEN @start AND @end AND {SPEND_FILTER}
                  AND (@category = '' OR category = @category)
                GROUP BY month ORDER BY month""",
            start=start, end=end, category=category or "",
        )

    def top_merchants(self, start, end, category=None, limit=5):
        return self._q(
            f"""SELECT COALESCE(merchant_name, raw_description) AS merchant, ROUND(SUM(amount), 2) AS spend, COUNT(*) AS txns
                FROM {self.table('transactions')}
                WHERE user_id = @user_id AND txn_date BETWEEN @start AND @end AND {SPEND_FILTER}
                  AND (@category = '' OR category = @category)
                GROUP BY merchant ORDER BY spend DESC LIMIT @limit""",
            start=start, end=end, category=category or "", limit=limit,
        )

    def merchant_spend(self, merchant, start, end):
        return self._q(
            f"""SELECT COALESCE(merchant_name, raw_description) AS merchant, ROUND(SUM(amount), 2) AS spend, COUNT(*) AS txns
                FROM {self.table('transactions')}
                WHERE user_id = @user_id AND txn_date BETWEEN @start AND @end AND direction = 'debit'
                  AND (LOWER(merchant_name) LIKE CONCAT('%', LOWER(@merchant), '%')
                       OR LOWER(raw_description) LIKE CONCAT('%', LOWER(@merchant), '%'))
                GROUP BY merchant ORDER BY spend DESC""",
            merchant=merchant, start=start, end=end,
        )

    def budget_status(self):
        return self._q(
            f"""SELECT category, monthly_limit, ROUND(spend_month_to_date, 2) AS spend_month_to_date,
                       ROUND(pct_used * 100, 1) AS pct_used
                FROM {self.table('v_budget_status')}
                WHERE user_id = @user_id ORDER BY pct_used DESC"""
        )

    def transactions(self, start, end, category=None, limit=100):
        return self._q(
            f"""SELECT transaction_id, txn_date, raw_description, merchant_name, amount, direction,
                       category, category_source, category_confidence
                FROM {self.table('transactions')}
                WHERE user_id = @user_id AND txn_date BETWEEN @start AND @end
                  AND (@category = '' OR category = @category)
                ORDER BY txn_date DESC, posted_at DESC LIMIT @limit""",
            start=start, end=end, category=category or "", limit=limit,
        )

    def alerts(self, limit=20):
        return self._q(
            f"""SELECT alert_id, alert_type, category, message, amount_spent, monthly_limit, created_at
                FROM {self.table('alerts')} WHERE user_id = @user_id
                ORDER BY created_at DESC LIMIT @limit""",
            limit=limit,
        )

    # -- categorization --------------------------------------------------
    def uncategorized(self, limit):
        return self._q(
            f"""SELECT transaction_id, raw_description, amount, direction, channel
                FROM {self.table('transactions')}
                WHERE user_id = @user_id AND category IS NULL
                ORDER BY txn_date DESC LIMIT @limit""",
            limit=limit,
        )

    def apply_categories(self, updates):
        if not updates:
            return 0
        bq = self._bq
        rows = bq.ArrayQueryParameter("rows", "STRUCT", [
            bq.StructQueryParameter(
                None,
                bq.ScalarQueryParameter("transaction_id", "STRING", u.transaction_id),
                bq.ScalarQueryParameter("merchant_name", "STRING", u.merchant_name),
                bq.ScalarQueryParameter("category", "STRING", u.category),
                bq.ScalarQueryParameter("confidence", "FLOAT64", u.confidence),
            )
            for u in updates
        ])
        job = self.client.query(
            f"""MERGE {self.table('transactions')} t
                USING UNNEST(@rows) u ON t.transaction_id = u.transaction_id AND t.user_id = @user_id
                WHEN MATCHED THEN UPDATE SET
                  merchant_name = u.merchant_name, category = u.category,
                  category_source = 'gemini', category_confidence = u.confidence""",
            job_config=bq.QueryJobConfig(query_parameters=[
                rows, bq.ScalarQueryParameter("user_id", "STRING", self.user_id)]),
        )
        job.result()
        return job.num_dml_affected_rows or 0

    def categorization_accuracy(self):
        rows = self._q(
            f"""SELECT COUNT(*) AS evaluated,
                       COUNTIF(t.category = l.true_category) AS correct,
                       ROUND(SAFE_DIVIDE(COUNTIF(t.category = l.true_category), COUNT(*)) * 100, 1) AS accuracy_pct,
                       ROUND(AVG(t.category_confidence), 3) AS avg_confidence
                FROM {self.table('transactions')} t
                JOIN {self.table('category_labels')} l USING (transaction_id)
                WHERE t.user_id = @user_id AND t.category_source = 'gemini'"""
        )
        misses = self._q(
            f"""SELECT t.raw_description, t.category AS predicted, l.true_category AS expected
                FROM {self.table('transactions')} t
                JOIN {self.table('category_labels')} l USING (transaction_id)
                WHERE t.user_id = @user_id AND t.category_source = 'gemini' AND t.category != l.true_category
                LIMIT 10"""
        )
        return {**rows[0], "sample_misses": misses}

    # -- receipts --------------------------------------------------------
    def find_transaction_for_receipt(self, total, on, days=3):
        rows = self._q(
            f"""SELECT transaction_id, txn_date, raw_description, amount
                FROM {self.table('transactions')}
                WHERE user_id = @user_id AND direction = 'debit'
                  AND ABS(amount - CAST(@total AS NUMERIC)) <= 0.01
                  AND txn_date BETWEEN DATE_SUB(@on, INTERVAL @days DAY) AND DATE_ADD(@on, INTERVAL @days DAY)
                ORDER BY ABS(DATE_DIFF(txn_date, @on, DAY)) LIMIT 1""",
            total=float(total), on=on, days=days,
        )
        return rows[0] if rows else None

    def insert_receipt(self, row):
        # A load job (not streaming) so the row is immediately visible to DML and free of charge.
        bq = self._bq
        job = self.client.load_table_from_json(
            [row], f"{self.project}.{self.dataset}.receipts",
            job_config=bq.LoadJobConfig(write_disposition=bq.WriteDisposition.WRITE_APPEND),
        )
        job.result()

    def tag_transaction(self, transaction_id: str, merchant: str, category: str) -> None:
        self._q(
            f"""UPDATE {self.table('transactions')}
                SET merchant_name = @merchant, category = @category, category_source = 'receipt', category_confidence = 1.0
                WHERE transaction_id = @tid AND user_id = @user_id""",
            merchant=merchant, category=category, tid=transaction_id,
        )


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def dumps(rows: Any) -> str:
    return json.dumps(rows, default=_plain, indent=None)
