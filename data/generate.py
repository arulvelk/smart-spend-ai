"""Generate SmartSpend synthetic data into data/out/.

    python generate.py                     # 12 months ending yesterday
    python generate.py --months 6 --receipts 30 --end 2026-10-31

Outputs (NDJSON, ready for `bq load` or load_bigquery.py):
    out/transactions.ndjson      bank-feed rows; the last N days are left uncategorized
    out/category_labels.ndjson   ground truth for measuring categorizer accuracy
    out/budgets.ndjson
    out/receipts/<id>.jpg        receipt photos, plus <id>.json with the true parse
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from smartspend_data import budget_rows, generate_range
from smartspend_data.receipts import render


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--end", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    p.add_argument("--months", type=int, default=12)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--uncategorized-days", type=int, default=30,
                   help="Leave category blank for the most recent N days so the agent has work to do")
    p.add_argument("--receipts", type=int, default=24, help="Number of receipt images to render")
    p.add_argument("--out", type=Path, default=Path(__file__).parent / "out")
    a = p.parse_args()

    start = (a.end.replace(day=1) - timedelta(days=31 * (a.months - 1))).replace(day=1)
    out = a.out
    (out / "receipts").mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    cutoff = a.end - timedelta(days=a.uncategorized_days)

    txns = list(generate_range(start, a.end, seed=a.seed))
    with open(out / "transactions.ndjson", "w", encoding="utf-8") as f:
        for t in txns:
            f.write(json.dumps(t.bq_row(categorized=t.txn_date <= cutoff, ingested_at=now)) + "\n")
    with open(out / "category_labels.ndjson", "w", encoding="utf-8") as f:
        for t in txns:
            f.write(json.dumps(t.label_row()) + "\n")
    with open(out / "budgets.ndjson", "w", encoding="utf-8") as f:
        for b in budget_rows(start):
            f.write(json.dumps(b) + "\n")

    with_receipts = [t for t in txns if t.receipt]
    rng = random.Random(a.seed)
    # Bias the sample toward recent receipts, since those are the ones a user would upload.
    recent = [t for t in with_receipts if t.txn_date > cutoff]
    older = [t for t in with_receipts if t.txn_date <= cutoff]
    picked = rng.sample(recent, min(len(recent), a.receipts // 2))
    picked += rng.sample(older, min(len(older), a.receipts - len(picked)))
    for i, t in enumerate(picked):
        rid = "rcpt_" + t.transaction_id[4:]
        render(t.receipt, out / "receipts" / f"{rid}.jpg", seed=a.seed + i)
        truth = {"receipt_id": rid, "transaction_id": t.transaction_id, **t.receipt}
        (out / "receipts" / f"{rid}.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")

    debits = [t for t in txns if t.direction == "debit"]
    by_cat = Counter()
    for t in debits:
        by_cat[t.true_category] += t.amount
    print(f"{len(txns)} transactions {start} .. {a.end}  ({sum(t.txn_date > cutoff for t in txns)} uncategorized)")
    print(f"{len(picked)} receipts rendered -> {out / 'receipts'}")
    for cat, amt in by_cat.most_common():
        print(f"  {cat:<15} ${amt:>10,.2f}")


if __name__ == "__main__":
    main()
