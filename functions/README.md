# functions/ — event-driven jobs (Cloud Functions gen2 + Cloud Scheduler)

Built in **step 3**:

- **daily_ingest** (Cloud Scheduler, 06:00 daily) — pulls yesterday's synthetic bank feed using `data/smartspend_data.generate_day`, MERGEs it into `transactions` by `transaction_id` (idempotent), then calls the API's `/categorize`.
- **budget_alerts** (runs after ingest) — reads `v_budget_status`, writes to `alerts` at 80% and 100% of budget, and publishes to the `smartspend-alerts` Pub/Sub topic.
