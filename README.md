# SmartSpend AI

A personal budgeting and financial-advisor app built serverless and cloud-native on **Google Cloud**.

- **Vertex AI (Gemini)** is the reasoning engine: it parses receipt photos, cleans and categorizes messy bank descriptors like `SQ *BLUE BOTTLE CO 0423`, and classifies what the user is asking.
- **Cloud Run** hosts the FastAPI backend, the LangGraph advisor agent, and the Next.js UI.
- **BigQuery** is the financial data warehouse for transactions, receipts, budgets, and alerts, and it runs the analytics SQL.
- **Cloud Scheduler + Cloud Functions** run the daily transaction ingest and send proactive budget alerts.

All data is **synthetic**. A deterministic generator produces 12 months of realistic, messy transactions and receipt photos.

See [docs/architecture.md](docs/architecture.md) for the diagram, data model, cost guardrails, and security notes.

## Repository layout

| Folder | What it contains | Status |
|---|---|---|
| `infra/terraform/` | APIs, BigQuery dataset, tables and views, GCS bucket, Artifact Registry, Pub/Sub, service accounts, billing budget | ✅ step 1 |
| `data/` | Synthetic generator, receipt renderer, and BigQuery loader, with tests | ✅ step 1 |
| `agent/` | LangGraph advisor agent on Gemini | step 2 |
| `api/` | FastAPI service on Cloud Run | step 2 |
| `ui/` | Next.js dashboard on Cloud Run | step 3 |
| `functions/` | Daily ingest and budget-alert Cloud Functions | step 3 |
| `scripts/` | `bootstrap.ps1`, which runs the one-time setup | ✅ step 1 |

## Prerequisites (Windows)

```powershell
winget install Google.CloudSDK
winget install Hashicorp.Terraform
winget install astral-sh.uv
```

Open a new terminal after installing so PATH updates.

## One-time GCP setup

1. **Create the project and link the trial billing account:**

   ```powershell
   gcloud auth login
   gcloud auth application-default login
   gcloud billing accounts list                      # copy the ACCOUNT_ID
   $P = "smartspend-ai-$(Get-Random -Maximum 999999)"
   gcloud projects create $P --name "SmartSpend AI"
   gcloud billing projects link $P --billing-account XXXXXX-XXXXXX-XXXXXX
   ```

2. **Provision the infrastructure, generate data, and load BigQuery:**

   ```powershell
   ./scripts/bootstrap.ps1 -ProjectId $P -BillingAccount XXXXXX-XXXXXX-XXXXXX
   ```

   This enables the APIs, creates everything in `infra/terraform`, generates the synthetic data, loads it into `smartspend.*`, and uploads 24 sample receipts to `gs://$P-smartspend-receipts/samples/`.

3. **Try a query in the BigQuery console:**

   ```sql
   SELECT * FROM smartspend.v_budget_status ORDER BY pct_used DESC;
   ```

## Working with the data locally

```powershell
cd data
uv sync
uv run pytest                     # generator and schema tests
uv run python generate.py --help  # months, seed, number of receipts, uncategorized window
```

The most recent 30 days are loaded **uncategorized** on purpose. Those are the rows the Gemini categorizer fills in during step 2. `category_labels` keeps the true answers so we can report categorization accuracy.

## Tear down

```powershell
terraform -chdir=infra/terraform destroy -var "project_id=$P"
gcloud projects delete $P
```
