# Architecture

```mermaid
flowchart LR
    user([User]) --> ui[Next.js UI<br/>Cloud Run, public]
    ui -- "server-side proxy,<br/>ID token" --> api[FastAPI + LangGraph agent<br/>Cloud Run, private]
    api -- "intent, categorization,<br/>receipt parsing" --> gemini[Gemini Flash<br/>Vertex AI]
    api -- "SQL tools" --> bq[(BigQuery<br/>smartspend dataset)]
    api -- "receipt photos" --> gcs[(Cloud Storage)]
    sched[Cloud Scheduler<br/>daily 06:00] -- "OIDC token" --> job[smartspend-daily-job<br/>Cloud Function gen2]
    job -- "MERGE new transactions,<br/>read v_budget_status, write alerts" --> bq
    job -- "POST /categorize<br/>(ID token)" --> api
    job --> pubsub[[Pub/Sub<br/>smartspend-alerts]]
```

## BigQuery model

| Object | Kind | Purpose |
|---|---|---|
| `transactions` | table, monthly partitions on `txn_date`, clustered by `user_id, category` | Bank feed. `category`, `merchant_name`, `category_source`, `category_confidence` are filled by Gemini |
| `receipts` | table, nested `line_items` | Gemini multimodal parse of uploaded receipts, matched to a transaction |
| `budgets` | table | Monthly limit per category, versioned by `effective_from` |
| `alerts` | table, daily partitions | Proactive alerts from the scheduled job |
| `category_labels` | table | Synthetic ground truth, used to measure categorizer accuracy |
| `v_monthly_category_spend` | view | Spend by month and category (excludes transfers and income) |
| `v_budget_status` | view | Month-to-date spend against the current budget |

## Cost guardrails ($200 trial credit)

- Cloud Run and Cloud Functions scale to zero, so idle cost is $0.
- Gemini **Flash** models only; categorization is batched (many transactions per call).
- BigQuery stays inside the free tier (10 GB storage, 1 TB queries/month) at this data size.
- Billing budget alert at 50/90/100% of $50/month (Terraform `budget.tf`).
- Receipts bucket deletes objects after 90 days; Artifact Registry keeps the 5 newest images.

## Daily job

1. **Ingest:** generates the synthetic bank feed for every day since the last load (catch-up, at most 31 days), loads it into an expiring staging table, and `MERGE`s it into `transactions` on `transaction_id`, so re-runs never create duplicates.
2. **Categorize:** calls the private API's `/categorize` with a Google-signed ID token.
3. **Alert:** raises at most one alert per category per type per month: `budget_exceeded` (100% or more), `budget_threshold` (80% or more), and `on_pace_to_exceed` (from day 5, a straight-line projection more than 10% over the limit). Alerts go to BigQuery and Pub/Sub.

## Security

- One service account per runtime with least privilege (see `infra/terraform/iam.tf`).
- Dataset-level, not project-level, BigQuery write access.
- Receipts bucket has public access prevention enforced.
- The API and the function are private (`--no-allow-unauthenticated`). Only the UI, job and scheduler service accounts hold `roles/run.invoker`. The UI is public, with an optional password, and reaches only allow-listed API paths.
- Synthetic data only: no real financial data ever enters the project.
