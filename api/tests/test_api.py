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
                                  lambda data, ct, name: uploads.append(name) or f"gs://bucket/{name}")
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
