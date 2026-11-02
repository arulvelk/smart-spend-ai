# api/ — FastAPI backend on Cloud Run

One Cloud Run service hosts the REST API and the LangGraph agent (`../agent`). It runs as the `smartspend-api` service account, which can read and write only the `smartspend` dataset and the receipts bucket, and call Vertex AI.

| Method | Path | What it does |
|---|---|---|
| GET | `/health` | Liveness, model and dataset in use |
| GET | `/transactions?month=YYYY-MM&category=&account_id=` | Transactions for a month, optionally for one account |
| GET | `/analytics/categories?month=YYYY-MM` | Spend by category and top merchants |
| GET | `/analytics/monthly?category=` | 12-month spend trend |
| GET | `/budgets/status` | Month-to-date spend vs. budget (`v_budget_status`) |
| GET | `/alerts` | Alerts from the daily job |
| POST | `/chat` | `{"message": "...", "history": [...]}` → advisor answer, intent and the data used |
| POST | `/categorize?limit=200` | Categorize pending transactions with Gemini |
| GET | `/categorize/accuracy` | Gemini's categories vs. synthetic ground truth |
| POST | `/receipts` | Multipart image upload → GCS → Gemini parse → match to transaction → BigQuery |
| POST | `/receipts/{id}/transaction` | Turn an unmatched receipt into a transaction on an account |
| GET, POST | `/accounts` | List accounts and cards with their transaction counts; add one |
| POST | `/transactions` | Add a transaction by hand (Gemini cleans the merchant and categorizes it unless you pick a category) |
| PATCH | `/transactions/{id}/category` | Override a category (`category_source = 'user'`) |
| POST | `/statements/preview` | Multipart CSV, PDF or image (10 MB max) → GCS → parsed rows, flagged duplicates, warnings. Nothing is saved yet |
| POST | `/statements/import` | Save the rows you kept: dedupe, Gemini categorization, load job + `MERGE`, and an `imports` record |
| GET | `/imports` · POST `/imports/{id}/undo` | Import history; undo deletes exactly that import's rows |

### How statements are read

CSV exports (Chase, Amex, most banks) are parsed with rules: the header row is found even after preamble lines, and both a single signed amount column and separate debit/credit columns are handled. Which sign means "purchase" is decided by the majority of rows, since card and bank exports disagree. PDFs, photos and CSV layouts the rules don't recognize go to Gemini with a structured-output schema. Each row gets a deterministic ID from the account, date, description, amount and its occurrence count, so uploading the same statement twice adds nothing and two identical coffees on the same day both survive.

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
