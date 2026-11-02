import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent" / "tests"))
from fakes import PIZZA_RECEIPT, FakeLLM, FakeWarehouse  # noqa: E402

from smartspend_agent import Settings, build_advisor  # noqa: E402
from smartspend_api.main import Services, app  # noqa: E402


@pytest.fixture
def client():
    settings = Settings(project="test", today_override=date(2026, 11, 15))
    llm = FakeLLM(intent={"intent": "budget_status", "period": "this_month"}, receipt=PIZZA_RECEIPT,
                  answer="Dining is at 180% of budget.")
    wh = FakeWarehouse()
    uploads = []
    app.state.services = Services(settings, llm, wh, build_advisor(llm, wh, settings),
                                  lambda data, ct, path: uploads.append(path) or f"gs://bucket/{path}")
    with TestClient(app) as c:
        c.wh, c.uploads = wh, uploads
        yield c
    del app.state.services


def test_health(client):
    assert client.get("/health").json()["ok"] is True


def test_month_range(client):
    r = client.get("/analytics/categories", params={"month": "2026-02"}).json()
    assert (r["start"], r["end"]) == ("2026-02-01", "2026-02-28")
    r = client.get("/analytics/categories").json()
    assert (r["start"], r["end"]) == ("2026-11-01", "2026-11-15")
    assert client.get("/transactions", params={"month": "2026-13"}).status_code == 422


def test_chat_returns_grounded_answer(client):
    r = client.post("/chat", json={"message": "Am I over budget?"}).json()
    assert r["answer"] == "Dining is at 180% of budget."
    assert r["intent"]["intent"] == "budget_status"
    assert r["data"]["budget_status"][0]["category"] == "Dining"


def test_chat_validates_input(client):
    assert client.post("/chat", json={"message": ""}).status_code == 422
    assert client.post("/chat", json={"message": "x" * 1001}).status_code == 422


def test_categorize(client):
    r = client.post("/categorize").json()
    assert r["categorized"] == 2


def test_receipt_upload(client):
    r = client.post("/receipts", files={"file": ("r.jpg", b"\xff\xd8fake", "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matched_transaction"]["transaction_id"] == "txn_pizza"
    assert body["gcs_uri"].startswith("gs://bucket/") and len(client.uploads) == 1


def test_receipt_rejects_non_images(client):
    r = client.post("/receipts", files={"file": ("r.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 415


# ---------------------------------------------------------------- your own data
CSV = b"""Transaction Date,Post Date,Description,Category,Type,Amount
10/28/2026,10/29/2026,SQ *BLUE BOTTLE COFFEE,Food & Drink,Sale,-6.25
10/27/2026,10/28/2026,AMZN Mktp US*2K4L7,Shopping,Sale,-42.10
"""


def test_create_account_and_list(client):
    r = client.post("/accounts", json={"name": "Chase Sapphire", "type": "credit_card", "last4": "9921"})
    assert r.status_code == 201 and r.json()["account_id"].startswith("acct_") and r.json()["is_demo"] is False
    names = [a["name"] for a in client.get("/accounts").json()["items"]]
    assert "Chase Sapphire" in names
    assert client.post("/accounts", json={"name": "x", "type": "crypto"}).status_code == 422


def test_manual_transaction_is_categorized_by_gemini_unless_user_picks(client):
    r = client.post("/transactions", json={"account_id": "acct_amex", "txn_date": "2026-11-10",
                                           "description": "Blue Bottle Coffee", "amount": 6.5})
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["source"] == "manual" and row["category"] == "Coffee" and row["category_source"] == "gemini"
    r = client.post("/transactions", json={"account_id": "acct_amex", "txn_date": "2026-11-10",
                                           "description": "Gift for mom", "amount": 40, "category": "Shopping"})
    assert r.json()["category_source"] == "user"
    assert len(client.wh.rows) == 2


def test_manual_transaction_validation(client):
    base = {"account_id": "acct_amex", "txn_date": "2026-11-10", "description": "x", "amount": 5}
    assert client.post("/transactions", json={**base, "account_id": "nope"}).status_code == 404
    assert client.post("/transactions", json={**base, "txn_date": "2026-12-01"}).status_code == 422
    assert client.post("/transactions", json={**base, "amount": -5}).status_code == 422
    assert client.post("/transactions", json={**base, "category": "Lottery"}).status_code == 422


def test_csv_statement_preview_import_dedupe_and_undo(client):
    files = {"file": ("activity.csv", CSV, "text/csv")}
    prev = client.post("/statements/preview", data={"account_id": "acct_amex"}, files=files).json()
    assert prev["parser"] == "csv-rules" and len(prev["rows"]) == 2
    assert not any(r["duplicate"] for r in prev["rows"])
    assert client.uploads[-1].startswith("statements/demo-user/")

    body = {k: prev[k] for k in ("account_id", "filename", "format", "gcs_uri", "parser")}
    body.update(rows_parsed=2, rows=[{k: r[k] for k in ("txn_date", "description", "amount", "direction")}
                                     for r in prev["rows"]])
    first = client.post("/statements/import", json=body).json()
    assert (first["inserted"], first["skipped"]) == (2, 0)
    assert {t["category"] for t in client.wh.rows} == {"Coffee", "Shopping"}

    # Uploading the same statement again: preview flags duplicates, import adds nothing.
    again = client.post("/statements/preview", data={"account_id": "acct_amex"}, files=files).json()
    assert all(r["duplicate"] for r in again["rows"])
    assert client.post("/statements/import", json=body).json()["inserted"] == 0

    undo = client.post(f"/imports/{first['import_id']}/undo").json()
    assert undo["deleted"] == 2 and client.wh.rows == []
    assert client.get("/imports").json()["items"][0]["status"] == "undone"


def test_pdf_statement_uses_gemini_and_warns_on_account_mismatch(client):
    files = {"file": ("october.pdf", b"%PDF-1.7 fake", "application/pdf")}
    prev = client.post("/statements/preview", data={"account_id": "cc-001"}, files=files).json()
    assert prev["format"] == "pdf" and prev["parser"] == "gemini-3.8-flash"
    assert len(prev["rows"]) == 3 and len({r["transaction_id"] for r in prev["rows"]}) == 3
    assert any("ending 1009" in w for w in prev["warnings"])


def test_statement_rejects_other_files(client):
    files = {"file": ("notes.docx", b"x", "application/octet-stream")}
    assert client.post("/statements/preview", data={"account_id": "acct_amex"}, files=files).status_code == 415


def test_change_category(client):
    client.post("/transactions", json={"account_id": "acct_amex", "txn_date": "2026-11-10",
                                       "description": "Venmo J Smith", "amount": 20})
    tid = client.wh.rows[0]["transaction_id"]
    r = client.patch(f"/transactions/{tid}/category", json={"category": "Dining"})
    assert r.json()["category_source"] == "user" and client.wh.rows[0]["category"] == "Dining"
    assert client.patch("/transactions/nope/category", json={"category": "Dining"}).status_code == 404


def test_create_transaction_from_unmatched_receipt(client):
    client.wh.receipts.append({"receipt_id": "rcpt_abc", "merchant_name": "Corner Deli", "receipt_date": "2026-11-09",
                               "total": 12.4, "category": "Dining", "matched_transaction_id": None})
    r = client.post("/receipts/rcpt_abc/transaction", json={"account_id": "acct_amex"})
    assert r.status_code == 201 and r.json()["source"] == "receipt" and r.json()["amount"] == "12.40"
    assert client.wh.receipt("rcpt_abc")["matched_transaction_id"] == r.json()["transaction_id"]
    assert client.post("/receipts/rcpt_abc/transaction", json={"account_id": "acct_amex"}).status_code == 409
