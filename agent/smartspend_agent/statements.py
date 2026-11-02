"""Turn a bank or card statement (CSV, PDF or photo) into transaction rows.

CSV exports are parsed with rules first: they are exact and free. Anything the
rules can't read confidently (an unusual CSV, a PDF statement, a photo) goes to
Gemini with a structured-output schema. Either way, the user previews the rows
before anything is written.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .llm import LLM

DATE_HEADERS = ("transaction date", "trans. date", "trans date", "date", "posting date", "post date", "posted date")
DESC_HEADERS = ("description", "merchant", "payee", "name", "details", "transaction", "memo")
AMOUNT_HEADERS = ("amount", "transaction amount", "amount (usd)")
DEBIT_HEADERS = ("debit", "withdrawal", "withdrawals", "debit amount", "charges")
CREDIT_HEADERS = ("credit", "deposit", "deposits", "credit amount", "payments")
DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%m-%d-%Y", "%d %b %Y", "%b %d, %Y", "%d-%b-%Y", "%Y/%m/%d")


class StatementRow(BaseModel):
    txn_date: date
    description: str = Field(max_length=200)
    amount: float = Field(ge=0.01, description="Always positive; see direction")
    direction: Literal["debit", "credit"]


class StatementParse(BaseModel):
    """Gemini's view of a statement."""
    rows: list[StatementRow]
    account_last4: Optional[str] = Field(None, description="Last 4 digits of the card or account, if printed")
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class ParsedStatement(BaseModel):
    rows: list[StatementRow]
    parser: str  # "csv-rules" or the Gemini model name
    account_last4: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


def _norm(h: str) -> str:
    return re.sub(r"\s+", " ", h.strip().lower())


def _find(headers: list[str], names: tuple[str, ...]) -> int | None:
    normed = [_norm(h) for h in headers]
    for name in names:  # names are in priority order
        if name in normed:
            return normed.index(name)
    return None


def _money(text: str) -> float | None:
    t = text.strip().replace("$", "").replace(",", "").replace("USD", "").strip()
    if not t:
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _date(text: str) -> date | None:
    t = text.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def parse_csv_rules(text: str) -> ParsedStatement | None:
    """Parse common bank CSV layouts. Returns None when the layout isn't recognised."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    # Some banks put account info above the header; find the first line that looks like one.
    start = next((i for i, ln in enumerate(lines[:15])
                  if _find(next(csv.reader([ln])), DATE_HEADERS) is not None), None)
    if start is None:
        return None
    reader = csv.reader(io.StringIO("\n".join(lines[start:])))
    headers = next(reader)
    di, de = _find(headers, DATE_HEADERS), _find(headers, DESC_HEADERS)
    ai, dbi, cri = _find(headers, AMOUNT_HEADERS), _find(headers, DEBIT_HEADERS), _find(headers, CREDIT_HEADERS)
    if di is None or de is None or (ai is None and dbi is None):
        return None

    signed: list[tuple[date, str, float]] = []
    bad = 0
    for rec in reader:
        if len(rec) < len(headers):
            rec += [""] * (len(headers) - len(rec))
        d = _date(rec[di])
        if d is None:
            bad += 1
            continue
        if ai is not None:
            v = _money(rec[ai])
        else:  # separate debit / credit columns: debits are money out
            debit = _money(rec[dbi]) if dbi is not None else None
            credit = _money(rec[cri]) if cri is not None else None
            v = -abs(debit) if debit else (abs(credit) if credit else None)
        if v is None or v == 0:
            bad += 1
            continue
        signed.append((d, rec[de].strip()[:200], v))
    if not signed:
        return None

    warnings = [f"Skipped {bad} line(s) without a readable date or amount."] if bad else []
    # Sign conventions differ: most banks show purchases as negative, some card issuers as positive.
    # Whichever sign the majority of rows has is treated as money out.
    negatives = sum(1 for *_, v in signed if v < 0)
    purchases_negative = negatives >= len(signed) / 2 or ai is None
    if ai is not None and not purchases_negative:
        warnings.append("Most amounts are positive, so positive amounts were treated as purchases (common on card exports).")
    rows = [
        StatementRow(txn_date=d, description=desc, amount=round(abs(v), 2),
                     direction="debit" if (v < 0) == purchases_negative else "credit")
        for d, desc, v in signed
    ]
    return ParsedStatement(rows=rows, parser="csv-rules", warnings=warnings)


PROMPT = """You are reading a bank or credit-card statement.
Extract EVERY transaction line: date (YYYY-MM-DD), description exactly as printed, amount as a positive number,
and direction: "debit" for money out (purchases, fees, interest, withdrawals) or "credit" for money in
(payments to the card, refunds, deposits, interest earned).
If rows show only month and day, take the year from the statement period (watch for periods that cross New Year).
Skip balances, subtotals, rewards summaries and anything that is not a transaction.
Also return the last 4 digits of the account or card if printed, and the statement period."""


def parse_with_gemini(llm: LLM, data: bytes, mime_type: str, model_name: str) -> ParsedStatement:
    if mime_type.startswith("text/"):
        text = data.decode("utf-8", errors="replace")[:200_000]
        out = llm.structured(PROMPT + "\n\nStatement (CSV/text):\n" + text, StatementParse)
    else:
        out = llm.structured(PROMPT, StatementParse, image=data, mime_type=mime_type)
    return ParsedStatement(rows=out.rows, parser=model_name, account_last4=out.account_last4)


def parse_statement(llm: LLM, data: bytes, mime_type: str, model_name: str) -> ParsedStatement:
    if mime_type in ("text/csv", "application/vnd.ms-excel", "text/plain"):
        rules = parse_csv_rules(data.decode("utf-8-sig", errors="replace"))
        if rules and rules.rows:
            return rules
        parsed = parse_with_gemini(llm, data, "text/csv", model_name)
        parsed.warnings.append("The CSV layout wasn't recognised, so Gemini read it. Check the rows carefully.")
        return parsed
    return parse_with_gemini(llm, data, mime_type, model_name)


def _clean_desc(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().upper())


def statement_ids(user_id: str, account_id: str, rows: list[StatementRow]) -> list[str]:
    """Deterministic ids, so uploading the same statement twice adds nothing.

    Two identical rows in one statement (two $5.25 coffees on the same day) stay
    distinct through their occurrence number.
    """
    seen: dict[str, int] = {}
    ids = []
    for r in rows:
        base = f"{user_id}|{account_id}|{r.txn_date}|{r.amount:.2f}|{r.direction}|{_clean_desc(r.description)}"
        n = seen.get(base, 0)
        seen[base] = n + 1
        ids.append("txn_s_" + hashlib.sha1(f"{base}|{n}".encode()).hexdigest()[:16])
    return ids
