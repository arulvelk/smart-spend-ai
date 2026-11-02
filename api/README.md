# api/ — FastAPI backend (Cloud Run)

Built in **step 2**. Planned endpoints:

| Method | Path | What it does |
|---|---|---|
| GET | `/transactions` | Paged transactions from BigQuery, filterable by month/category |
| GET | `/analytics/monthly` | Spend by month and category (`v_monthly_category_spend`) |
| GET | `/budgets/status` | Month-to-date spend vs. budget (`v_budget_status`) |
| POST | `/receipts` | Upload a receipt photo to GCS, parse it with Gemini, match it to a transaction |
| POST | `/chat` | Hand a question to the LangGraph advisor agent |
| POST | `/categorize` | Categorize uncategorized transactions with Gemini |

Runs as the `smartspend-api` service account (BigQuery dataset editor, Vertex AI user, receipts bucket).
