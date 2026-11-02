# functions/ — daily job (Cloud Functions gen2 + Cloud Scheduler)

`smartspend-daily-job` runs every day at 06:00 America/Los_Angeles. Cloud Scheduler calls it over HTTP with an OIDC token for the `smartspend-scheduler` service account. The function runs as `smartspend-jobs`.

1. **Ingest.** Generates the synthetic bank feed (`data/smartspend_data.generate_day`) for every day since the last load, up to yesterday, catching up at most 31 days. It loads the rows into an expiring staging table and `MERGE`s them on `transaction_id`, so re-runs are idempotent.
2. **Categorize.** POSTs to the private API's `/categorize` with a Google-signed ID token.
3. **Alert.** Compares month-to-date spend with each budget and raises each alert type at most once per category per month: `budget_exceeded`, `budget_threshold` (80%), and `on_pace_to_exceed`, a straight-line projection that applies from day 5. Alerts are written to BigQuery and published to the `smartspend-alerts` Pub/Sub topic.

The planning logic is in `daily_job/job.py` and is unit-tested (`uv run pytest functions/tests`). Deploy with `./scripts/deploy_jobs.ps1 -ProjectId <id>`, which copies `data/smartspend_data` in next to the function code.
