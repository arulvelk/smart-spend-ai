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
    def transactions(self, start: date, end: date, category: str | None = None, limit: int = 100,
                     account_id: str | None = None) -> list[dict]: ...
    def uncategorized(self, limit: int) -> list[dict]: ...
    def apply_categories(self, updates: list[CategoryUpdate]) -> int: ...
    def categorization_accuracy(self) -> dict: ...
    def find_transaction_for_receipt(self, total: float, on: date, days: int = 3) -> dict | None: ...
    def insert_receipt(self, row: dict) -> None: ...
    def tag_transaction(self, transaction_id: str, merchant: str, category: str) -> None: ...
    def alerts(self, limit: int = 20) -> list[dict]: ...
    def accounts(self) -> list[dict]: ...
    def create_account(self, row: dict) -> None: ...
    def insert_transactions(self, rows: list[dict]) -> int: ...
    def existing_ids(self, ids: list[str]) -> set[str]: ...
    def set_category(self, transaction_id: str, category: str) -> int: ...
    def record_import(self, row: dict) -> None: ...
    def imports(self, limit: int = 20) -> list[dict]: ...
    def undo_import(self, import_id: str) -> int: ...
    def receipt(self, receipt_id: str) -> dict | None: ...
    def link_receipt(self, receipt_id: str, transaction_id: str) -> None: ...


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

    def transactions(self, start, end, category=None, limit=100, account_id=None):
        return self._q(
            f"""SELECT transaction_id, account_id, txn_date, raw_description, merchant_name, amount, direction,
                       category, category_source, category_confidence, source
                FROM {self.table('transactions')}
                WHERE user_id = @user_id AND txn_date BETWEEN @start AND @end
                  AND (@category = '' OR category = @category)
                  AND (@account = '' OR account_id = @account)
                ORDER BY txn_date DESC, ingested_at DESC LIMIT @limit""",
            start=start, end=end, category=category or "", account=account_id or "", limit=limit,
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


    # -- accounts and your own data --------------------------------------
    def accounts(self):
        return self._q(
            f"""SELECT a.account_id, a.name, a.type, a.institution, a.last4, a.is_demo,
                       COUNT(t.transaction_id) AS txns, MAX(t.txn_date) AS last_txn_date
                FROM {self.table('accounts')} a
                LEFT JOIN {self.table('transactions')} t
                  ON t.account_id = a.account_id AND t.user_id = a.user_id
                WHERE a.user_id = @user_id
                GROUP BY 1, 2, 3, 4, 5, 6
                ORDER BY a.is_demo, a.name"""
        )

    def create_account(self, row):
        self._load("accounts", [row])

    def _load(self, table: str, rows: list[dict]) -> None:
        """Append with a load job: free, and rows are visible to DML immediately."""
        bq = self._bq
        schema = self.client.get_table(f"{self.project}.{self.dataset}.{table}").schema
        self.client.load_table_from_json(
            rows, f"{self.project}.{self.dataset}.{table}",
            job_config=bq.LoadJobConfig(schema=schema, write_disposition=bq.WriteDisposition.WRITE_APPEND),
        ).result()

    def insert_transactions(self, rows):
        """Insert rows whose transaction_id isn't there yet (idempotent)."""
        if not rows:
            return 0
        import uuid
        from datetime import timedelta

        bq = self._bq
        target = f"{self.project}.{self.dataset}.transactions"
        schema = self.client.get_table(target).schema
        staging = f"{self.project}.{self.dataset}._staging_api_{uuid.uuid4().hex[:8]}"
        tmp = bq.Table(staging, schema=schema)
        tmp.expires = datetime.now(timezone.utc) + timedelta(hours=1)
        self.client.create_table(tmp)
        try:
            self.client.load_table_from_json(rows, staging, job_config=bq.LoadJobConfig(schema=schema)).result()
            cols = ", ".join(f.name for f in schema)
            job = self.client.query(
                f"""MERGE `{target}` t USING `{staging}` s ON t.transaction_id = s.transaction_id
                    WHEN NOT MATCHED THEN INSERT ({cols}) VALUES ({cols})""")
            job.result()
            return job.num_dml_affected_rows or 0
        finally:
            self.client.delete_table(staging, not_found_ok=True)

    def existing_ids(self, ids):
        if not ids:
            return set()
        bq = self._bq
        rows = self._q(
            f"""SELECT transaction_id FROM {self.table('transactions')}
                WHERE user_id = @user_id AND transaction_id IN UNNEST(@ids)""",
            ids=bq.ArrayQueryParameter("ids", "STRING", ids),
        )
        return {r["transaction_id"] for r in rows}

    def set_category(self, transaction_id, category):
        job = self.client.query(
            f"""UPDATE {self.table('transactions')}
                SET category = @category, category_source = 'user', category_confidence = 1.0
                WHERE transaction_id = @tid AND user_id = @user_id""",
            job_config=self._bq.QueryJobConfig(query_parameters=[
                self._bq.ScalarQueryParameter("category", "STRING", category),
                self._bq.ScalarQueryParameter("tid", "STRING", transaction_id),
                self._bq.ScalarQueryParameter("user_id", "STRING", self.user_id),
            ]),
        )
        job.result()
        return job.num_dml_affected_rows or 0

    def record_import(self, row):
        self._load("imports", [row])

    def imports(self, limit=20):
        return self._q(
            f"""SELECT i.import_id, i.account_id, a.name AS account_name, i.filename, i.format, i.parser,
                       i.rows_parsed, i.rows_inserted, i.rows_skipped, i.status, i.created_at
                FROM {self.table('imports')} i
                LEFT JOIN {self.table('accounts')} a USING (account_id)
                WHERE i.user_id = @user_id ORDER BY i.created_at DESC LIMIT @limit""",
            limit=limit,
        )

    def undo_import(self, import_id):
        bq = self._bq
        params = [bq.ScalarQueryParameter("iid", "STRING", import_id),
                  bq.ScalarQueryParameter("user_id", "STRING", self.user_id)]
        job = self.client.query(
            f"DELETE FROM {self.table('transactions')} WHERE import_id = @iid AND user_id = @user_id",
            job_config=bq.QueryJobConfig(query_parameters=params))
        job.result()
        self.client.query(
            f"UPDATE {self.table('imports')} SET status = 'undone' WHERE import_id = @iid AND user_id = @user_id",
            job_config=bq.QueryJobConfig(query_parameters=params)).result()
        return job.num_dml_affected_rows or 0

    def receipt(self, receipt_id):
        rows = self._q(
            f"""SELECT receipt_id, merchant_name, receipt_date, total, category, matched_transaction_id
                FROM {self.table('receipts')} WHERE receipt_id = @rid AND user_id = @user_id""",
            rid=receipt_id,
        )
        return rows[0] if rows else None

    def link_receipt(self, receipt_id, transaction_id):
        self._q(
            f"""UPDATE {self.table('receipts')} SET matched_transaction_id = @tid
                WHERE receipt_id = @rid AND user_id = @user_id""",
            tid=transaction_id, rid=receipt_id,
        )


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def dumps(rows: Any) -> str:
    return json.dumps(rows, default=_plain, indent=None)
