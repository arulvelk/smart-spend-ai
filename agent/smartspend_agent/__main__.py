"""Quick check that Gemini on Vertex AI is reachable with your credentials.

    uv run python -m smartspend_agent --project YOUR_PROJECT_ID [--model gemini-3.8-flash] [--location global]

Categorizes a few messy descriptors without touching BigQuery.
"""
import argparse

from .categorizer import categorize_rows
from .llm import Gemini

SAMPLES = [
    {"transaction_id": "t1", "raw_description": "SQ *BLUE BOTTLE CO 0423", "amount": 6.5, "direction": "debit", "channel": "card"},
    {"transaction_id": "t2", "raw_description": "UBER   *EATS HELP.UBER.COM", "amount": 31.2, "direction": "debit", "channel": "card"},
    {"transaction_id": "t3", "raw_description": "CHASE CREDIT CRD AUTOPAY PPD ID: 4411", "amount": 1450, "direction": "debit", "channel": "ach"},
    {"transaction_id": "t4", "raw_description": "PGANDE WEB ONLINE 88123", "amount": 121.4, "direction": "debit", "channel": "ach"},
]

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", required=True)
    p.add_argument("--model", default="gemini-3.8-flash")
    p.add_argument("--location", default="global")
    a = p.parse_args()
    for u in categorize_rows(Gemini(a.project, a.location, a.model), SAMPLES):
        print(f"{u.transaction_id}: {u.merchant_name:<25} {u.category:<15} {u.confidence:.2f}")
