"""Cloud Function (gen2, HTTP) run every morning by Cloud Scheduler.

1. Ingest: generate the synthetic bank feed for every day since the last load
   (catch-up, idempotent) and MERGE it into BigQuery by transaction_id.
2. Categorize: call the private API's /categorize with a Google-signed ID token.
3. Alert: compare month-to-date spend with budgets, write new alerts to BigQuery
   and publish them to Pub/Sub.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import functions_framework
import google.auth.transport.requests
import google.oauth2.id_token
import requests
from google.cloud import bigquery, pubsub_v1

from job import days_to_ingest, plan_alerts
from smartspend_data import USER_ID, generate_day

log = logging.getLogger("daily_job")
logging.basicConfig(level=logging.INFO)

PROJECT = os.environ.get("GCP_PROJECT", "")
DATASET = os.environ.get("BQ_DATASET", "smartspend")
API_URL = os.environ.get("API_URL", "")
ALERTS_TOPIC = os.environ.get("ALERTS_TOPIC", "smartspend-alerts")
SEED = int(os.environ.get("SEED", "42"))
INGEST_THROUGH = os.environ.get("INGEST_THROUGH", "yesterday")  # or "today"


def table(name: str) -> str:
    return f"{PROJECT}.{DATASET}.{name}"


def merge_rows(bq: bigquery.Client, target: str, key: str, rows: list[dict]) -> int:
    """Load rows to a short-lived staging table, then MERGE (insert only new keys)."""
    if not rows:
        return 0
    staging = table(f"_staging_{target}_{uuid.uuid4().hex[:8]}")
    schema = bq.get_table(table(target)).schema
    tmp = bigquery.Table(staging, schema=schema)
    tmp.expires = datetime.now(timezone.utc) + timedelta(hours=1)  # cleanup even if we crash
    bq.create_table(tmp)
    try:
        bq.load_table_from_json(rows, staging, job_config=bigquery.LoadJobConfig(schema=schema)).result()
        cols = ", ".join(f.name for f in schema)
        job = bq.query(f"""
            MERGE `{table(target)}` t USING `{staging}` s ON t.{key} = s.{key}
            WHEN NOT MATCHED THEN INSERT ({cols}) VALUES ({cols})""")
        job.result()
        return job.num_dml_affected_rows or 0
    finally:
        bq.delete_table(staging, not_found_ok=True)


def ingest(bq: bigquery.Client, today: date) -> dict:
    last = list(bq.query(
        f"SELECT MAX(txn_date) AS d FROM `{table('transactions')}` WHERE source IN ('backfill', 'daily_feed')"
    ).result())[0]["d"]
    through = today if INGEST_THROUGH == "today" else today - timedelta(days=1)
    days = days_to_ingest(last, through)
    now = datetime.now(timezone.utc)
    txns = [t for d in days for t in generate_day(d, seed=SEED, end=d, source="daily_feed")]
    inserted = merge_rows(bq, "transactions", "transaction_id",
                          [t.bq_row(categorized=False, ingested_at=now) for t in txns])
    merge_rows(bq, "category_labels", "transaction_id", [t.label_row() for t in txns])
    return {"days": [d.isoformat() for d in days], "generated": len(txns), "inserted": inserted}


def categorize() -> dict:
    if not API_URL:
        return {"skipped": "API_URL not set"}
    token = google.oauth2.id_token.fetch_id_token(google.auth.transport.requests.Request(), API_URL)
    r = requests.post(f"{API_URL}/categorize", params={"limit": 500},
                      headers={"Authorization": f"Bearer {token}"}, timeout=240)
    r.raise_for_status()
    return r.json()


def alerts(bq: bigquery.Client, today: date) -> dict:
    budgets = [dict(r) for r in bq.query(
        f"SELECT category, monthly_limit, spend_month_to_date FROM `{table('v_budget_status')}` WHERE user_id = @u",
        job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("u", "STRING", USER_ID)]),
    ).result()]
    month = today.replace(day=1)
    sent = {(r["category"], r["alert_type"]) for r in bq.query(
        f"SELECT category, alert_type FROM `{table('alerts')}` WHERE user_id = @u AND period_month = @m",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("u", "STRING", USER_ID), bigquery.ScalarQueryParameter("m", "DATE", month)]),
    ).result()}
    new = plan_alerts(budgets, today, sent)
    now = datetime.now(timezone.utc).isoformat()
    rows = [a.row(USER_ID, month, now) for a in new]
    if rows:
        bq.load_table_from_json(rows, table("alerts"), job_config=bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND)).result()
        publisher = pubsub_v1.PublisherClient()
        topic = publisher.topic_path(PROJECT, ALERTS_TOPIC)
        for row in rows:
            publisher.publish(topic, json.dumps(row).encode(), alert_type=row["alert_type"]).result(timeout=30)
    return {"raised": [r["message"] for r in rows]}


@functions_framework.http
def daily_job(request):
    today = date.today()
    bq = bigquery.Client(project=PROJECT)
    result = {"today": today.isoformat()}
    result["ingest"] = ingest(bq, today)
    result["categorize"] = categorize()
    result["alerts"] = alerts(bq, today)
    log.info(json.dumps(result))
    return result
