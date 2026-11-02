# ui/ — Next.js dashboard on Cloud Run

| Tab | What it shows |
|---|---|
| Overview | Month-to-date spend, last month, budgets over limit, Gemini accuracy; 12-month trend; budget progress; spend by category; alerts from the daily job; top merchants |
| Transactions | Messy bank descriptor → clean merchant and category, with the source (Gemini plus confidence, receipt, or seed); a button that runs Gemini categorization |
| Receipts | Upload a photo; Gemini extracts line items; the totals are checked; the receipt is matched to the card transaction |
| Advisor | Chat with the LangGraph agent, with a "How I answered" panel showing the intent, date range and BigQuery data used |

## How it talks to the API

The browser calls `/api/*` on the UI itself. A server-side route (`app/api/[...path]/route.ts`, `lib/server-api.ts`) forwards an allow-listed set of paths to the private `smartspend-api` Cloud Run service. It attaches a Google-signed ID token minted for the `smartspend-ui` service account. The API is never exposed publicly, and the browser never sees a credential.

Set `DEMO_PASSWORD` on the service to put the public demo behind a basic-auth prompt (any username).

## Run locally

```powershell
# terminal 1: the API (see api/README.md)
uv run uvicorn smartspend_api.main:app --port 8080
# terminal 2
cd ui
npm install
npm run dev   # http://localhost:3000, proxies to http://localhost:8080
```

## Deploy

```powershell
./scripts/deploy_ui.ps1 -ProjectId smartspend-ai-123456 [-DemoPassword something]
```
