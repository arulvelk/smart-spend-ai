# agent/ — LangGraph advisor (Gemini on Vertex AI)

Built in **step 2**. A LangGraph state graph:

1. **classify_intent** — Gemini decides whether the request is a spending question, a budget question, a receipt, or advice.
2. **tools** — parameterized BigQuery SQL tools (`spend_by_category`, `top_merchants`, `budget_status`, `compare_months`) plus `categorize_transactions` and `parse_receipt`.
3. **advise** — Gemini writes the answer, grounded only in tool results.

Packaged as a Python library that the API imports, so one Cloud Run service serves both and nothing extra stays warm.
