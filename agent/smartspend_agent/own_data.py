"""Add your own data: accounts, manual transactions, statement imports, receipts.

Every path ends in the same BigQuery `transactions` table, so the dashboard,
advisor and daily alerts pick the rows up with no extra work.
"""
from __future__ import annotations

import uuid
from datetime import date

from .categorizer import categorize_rows
from .llm import LLM
from .statements import StatementRow, statement_ids
from .warehouse import Warehouse, now_utc

CHANNEL_BY_TYPE = {"credit_card": "card", "checking": "card", "savings": "transfer", "cash": "cash"}


def txn_row(*, transaction_id: str, user_id: str, account: dict, txn_date: date, description: str,
            amount: float, direction: str, source: str, import_id: str | None = None,
            merchant: str | None = None, category: str | None = None, category_source: str | None = None,
            confidence: float | None = None) -> dict:
    now = now_utc()
    return {
        "transaction_id": transaction_id,
        "user_id": user_id,
        "account_id": account["account_id"],
        "txn_date": txn_date.isoformat(),
        "posted_at": now,
        "raw_description": description.strip()[:200],
        "merchant_name": merchant,
        "amount": f"{abs(amount):.2f}",
        "direction": direction,
        "currency": "USD",
        "channel": CHANNEL_BY_TYPE.get(account.get("type", ""), "card"),
        "category": category,
        "category_source": category_source if category else None,
        "category_confidence": confidence if category else None,
        "source": source,
        "ingested_at": now,
        "import_id": import_id,
    }


def categorize_new(llm: LLM, rows: list[dict]) -> None:
    """Fill merchant/category in place for rows the user didn't categorize."""
    pending = [r for r in rows if not r["category"]]
    if not pending:
        return
    updates = {u.transaction_id: u for u in categorize_rows(llm, [
        {"transaction_id": r["transaction_id"], "raw_description": r["raw_description"],
         "amount": float(r["amount"]), "direction": r["direction"], "channel": r["channel"]}
        for r in pending
    ])}
    for r in pending:
        u = updates.get(r["transaction_id"])
        if u:
            r.update(merchant_name=u.merchant_name, category=u.category,
                     category_source="gemini", category_confidence=u.confidence)


def find_account(wh: Warehouse, account_id: str) -> dict | None:
    return next((a for a in wh.accounts() if a["account_id"] == account_id), None)


def add_manual(llm: LLM, wh: Warehouse, *, user_id: str, account: dict, txn_date: date, description: str,
               amount: float, direction: str, category: str | None) -> dict:
    row = txn_row(transaction_id="txn_m_" + uuid.uuid4().hex[:16], user_id=user_id, account=account,
                  txn_date=txn_date, description=description, amount=amount, direction=direction,
                  source="manual", category=category, category_source="user", confidence=1.0)
    categorize_new(llm, [row])
    wh.insert_transactions([row])
    return row


def preview_statement(wh: Warehouse, *, user_id: str, account_id: str, rows: list[StatementRow]) -> list[dict]:
    ids = statement_ids(user_id, account_id, rows)
    existing = wh.existing_ids(ids)
    return [{"transaction_id": tid, **r.model_dump(mode="json"), "duplicate": tid in existing}
            for tid, r in zip(ids, rows)]


def import_statement(llm: LLM, wh: Warehouse, *, user_id: str, account: dict, rows: list[StatementRow],
                     filename: str, gcs_uri: str, fmt: str, parser: str, rows_parsed: int) -> dict:
    import_id = "imp_" + uuid.uuid4().hex[:12]
    ids = statement_ids(user_id, account["account_id"], rows)
    existing = wh.existing_ids(ids)
    new = [txn_row(transaction_id=tid, user_id=user_id, account=account, txn_date=r.txn_date,
                   description=r.description, amount=r.amount, direction=r.direction,
                   source="statement", import_id=import_id)
           for tid, r in zip(ids, rows) if tid not in existing]
    categorize_new(llm, new)
    inserted = wh.insert_transactions(new)
    wh.record_import({
        "import_id": import_id, "user_id": user_id, "account_id": account["account_id"],
        "filename": filename[:200], "gcs_uri": gcs_uri, "format": fmt, "parser": parser,
        "rows_parsed": rows_parsed, "rows_inserted": inserted, "rows_skipped": rows_parsed - inserted,
        "status": "imported", "created_at": now_utc(),
    })
    return {"import_id": import_id, "rows_parsed": rows_parsed, "inserted": inserted,
            "skipped": rows_parsed - inserted}


def transaction_from_receipt(wh: Warehouse, *, user_id: str, receipt: dict, account: dict) -> dict:
    """Create the card transaction a receipt describes, when the bank feed doesn't have it yet."""
    tid = "txn_r_" + receipt["receipt_id"].removeprefix("rcpt_")
    row = txn_row(transaction_id=tid, user_id=user_id, account=account,
                  txn_date=date.fromisoformat(str(receipt["receipt_date"])),
                  description=receipt["merchant_name"], amount=float(receipt["total"]), direction="debit",
                  source="receipt", merchant=receipt["merchant_name"], category=receipt["category"],
                  category_source="receipt", confidence=1.0)
    wh.insert_transactions([row])
    wh.link_receipt(receipt["receipt_id"], tid)
    return row
