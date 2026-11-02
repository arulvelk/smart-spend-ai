"""Load data/out/* into BigQuery and upload sample receipts to Cloud Storage.

    python load_bigquery.py --project YOUR_PROJECT_ID
    python load_bigquery.py --project YOUR_PROJECT_ID --skip-receipts

Uses Application Default Credentials (`gcloud auth application-default login`).
Tables are created by Terraform; this script replaces their contents
(WRITE_TRUNCATE), so it is safe to re-run. Careful: a full re-run also
replaces transactions you added yourself. Use --only to load single tables.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from google.cloud import bigquery, storage

ROOT = Path(__file__).resolve().parent
SCHEMAS = ROOT.parent / "infra" / "terraform" / "schemas"
TABLES = {
    "transactions": "transactions.ndjson",
    "category_labels": "category_labels.ndjson",
    "budgets": "budgets.ndjson",
    "accounts": "accounts.ndjson",
}


def schema_for(table: str) -> list[bigquery.SchemaField]:
    return [bigquery.SchemaField.from_api_repr(f) for f in json.loads((SCHEMAS / f"{table}.json").read_text())]


def load_tables(client: bigquery.Client, dataset: str, out: Path, only: list[str] | None = None) -> None:
    for table, fname in TABLES.items():
        if only and table not in only:
            continue
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            schema=schema_for(table),
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        with open(out / fname, "rb") as f:
            job = client.load_table_from_file(f, f"{client.project}.{dataset}.{table}", job_config=job_config)
        job.result()
        print(f"loaded {job.output_rows:>6} rows -> {dataset}.{table}")


def upload_receipts(project: str, bucket_name: str, out: Path) -> None:
    bucket = storage.Client(project=project).bucket(bucket_name)
    files = sorted((out / "receipts").glob("*.jpg"))
    for f in files:
        bucket.blob(f"samples/{f.name}").upload_from_filename(str(f), content_type="image/jpeg")
    print(f"uploaded {len(files)} receipts -> gs://{bucket_name}/samples/")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", required=True)
    p.add_argument("--dataset", default="smartspend")
    p.add_argument("--bucket", help="Defaults to <project>-smartspend-receipts (created by Terraform)")
    p.add_argument("--out", type=Path, default=ROOT / "out")
    p.add_argument("--skip-receipts", action="store_true")
    p.add_argument("--only", nargs="+", choices=list(TABLES),
                   help="Load just these tables, e.g. --only accounts (adds the demo accounts to an existing setup)")
    a = p.parse_args()

    client = bigquery.Client(project=a.project)
    load_tables(client, a.dataset, a.out, a.only)
    if a.only:
        return
    if not a.skip_receipts:
        upload_receipts(a.project, a.bucket or f"{a.project}-smartspend-receipts", a.out)

    view = f"`{a.project}.{a.dataset}.v_monthly_category_spend`"
    rows = client.query(
        f"SELECT category, ROUND(spend, 2) AS spend FROM {view} "
        f"WHERE month = (SELECT MAX(month) FROM {view}) ORDER BY spend DESC LIMIT 5"
    ).result()
    print("\nTop categories, latest month (seed-categorized rows only):")
    for r in rows:
        print(f"  {r.category:<15} ${r.spend:>9,.2f}")


if __name__ == "__main__":
    main()
