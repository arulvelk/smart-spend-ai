# agent/ — LangGraph advisor on Gemini (Vertex AI)

A Python package (`smartspend_agent`) imported by the API, so one Cloud Run service serves both.

```
START -> classify --(in scope)--> run_tools -> advise -> END
                  \--(out of scope / receipt help)--> respond_direct -> END
```

| Module | What it does |
|---|---|
| `graph.py` | LangGraph state graph. **classify** turns the question into a typed `Intent` (Gemini structured output). **run_tools** maps the intent to fixed BigQuery queries. **advise** has Gemini answer only from that data. |
| `warehouse.py` | Parameterized BigQuery SQL. The model never writes SQL, so answers are auditable and the chat box can't inject queries. |
| `categorizer.py` | Batches 40 messy descriptors per Gemini call, validates the categories against an enum, drops any id the model invents, and MERGEs the results into BigQuery. |
| `receipts.py` | Gemini multimodal receipt parsing, an independent arithmetic check, and matching to the card transaction by total and date (within 3 days). |
| `llm.py` | Google Gen AI SDK client on Vertex AI (`vertexai=True`), with temperature 0 and low thinking for cost. |

Configuration comes from environment variables: `GCP_PROJECT`, `BQ_DATASET`, `GEMINI_MODEL` (default `gemini-3.8-flash`), `GEMINI_LOCATION` (default `global`), and `RECEIPTS_BUCKET`.

Tests use in-memory fakes and need no GCP access: `uv run --package smartspend-agent pytest agent/tests`.
