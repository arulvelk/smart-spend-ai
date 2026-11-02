# api/ — FastAPI backend on Cloud Run

One Cloud Run service hosts the REST API and the LangGraph agent (`../agent`). It runs as the `smartspend-api` service account, which can read and write only the `smartspend` dataset and the receipts bucket, and call Vertex AI.

| Method | Path | What it does |
|---|---|---|
| GET | `/healthz` | Liveness, model and dataset in use |
| GET | `/transactions?month=YYYY-MM&category=` | Transactions for a month |
| GET | `/analytics/categories?month=YYYY-MM` | Spend by category and top merchants |
| GET | `/analytics/monthly?category=` | 12-month spend trend |
| GET | `/budgets/status` | Month-to-date spend vs. budget (`v_budget_status`) |
| GET | `/alerts` | Alerts from the daily job |
| POST | `/chat` | `{"message": "...", "history": [...]}` → advisor answer, intent and the data used |
| POST | `/categorize?limit=200` | Categorize pending transactions with Gemini |
| GET | `/categorize/accuracy` | Gemini's categories vs. synthetic ground truth |
| POST | `/receipts` | Multipart image upload → GCS → Gemini parse → match to transaction → BigQuery |

Interactive docs are served at `/docs`.

## Run locally (uses your gcloud credentials)

```powershell
$env:GCP_PROJECT = "smartspend-ai-789185"
uv sync --all-packages
uv run uvicorn smartspend_api.main:app --reload --port 8080
# open http://localhost:8080/docs
```

## Deploy to Cloud Run

```powershell
./scripts/deploy_api.ps1 -ProjectId smartspend-ai-789185
```

The script builds the image with Cloud Build (`api/Dockerfile`, using the `smartspend-build` service account), pushes it to Artifact Registry, and deploys `smartspend-api` with no public access, scale-to-zero, and at most 2 instances. Then it runs a smoke test through an authenticated proxy.
