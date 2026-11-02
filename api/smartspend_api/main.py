"""SmartSpend AI API (FastAPI on Cloud Run).

Run locally with Application Default Credentials:
    uv run --package smartspend-api uvicorn smartspend_api.main:app --reload --port 8080
then open http://localhost:8080/docs
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from smartspend_agent import Settings, build_advisor
from smartspend_agent.categorizer import categorize_pending
from smartspend_agent.graph import resolve_period
from smartspend_agent.receipts import process_receipt

log = logging.getLogger("smartspend")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

MAX_RECEIPT_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


@dataclass
class Services:
    settings: Settings
    llm: Any
    warehouse: Any
    advisor: Any
    upload_receipt: Any  # (bytes, content_type, name) -> gs:// uri


def build_services() -> Services:
    from google.cloud import storage

    from smartspend_agent.llm import Gemini
    from smartspend_agent.warehouse import BigQueryWarehouse

    s = Settings.from_env()
    llm = Gemini(s.project, s.gemini_location, s.gemini_model)
    wh = BigQueryWarehouse(s.project, s.dataset, s.user_id)
    bucket = storage.Client(project=s.project).bucket(s.receipts_bucket)

    def upload(data: bytes, content_type: str, name: str) -> str:
        blob = bucket.blob(f"uploads/{s.user_id}/{name}")
        blob.upload_from_string(data, content_type=content_type)
        return f"gs://{bucket.name}/{blob.name}"

    return Services(s, llm, wh, build_advisor(llm, wh, s), upload)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "services"):  # tests inject their own
        app.state.services = build_services()
        s = app.state.services.settings
        log.info("ready project=%s dataset=%s model=%s@%s", s.project, s.dataset, s.gemini_model, s.gemini_location)
    yield


app = FastAPI(title="SmartSpend AI", version="0.1.0", lifespan=lifespan,
              description="Budgeting and financial-advice API: Gemini on Vertex AI, BigQuery, Cloud Run.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def timing(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    response.headers["Server-Timing"] = f"app;dur={ms:.0f}"
    log.info("%s %s %s %.0fms", request.method, request.url.path, response.status_code, ms)
    return response


def services(request: Request) -> Services:
    return request.app.state.services


def _range(month: Optional[str], s: Settings) -> tuple[date, date]:
    """`month` is YYYY-MM; default is the current month to date."""
    if not month:
        return resolve_period("this_month", s.today)
    try:
        start = date.fromisoformat(f"{month}-01")
    except ValueError:
        raise HTTPException(422, "month must be YYYY-MM")
    next_month = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    end = next_month - timedelta(days=1)
    return start, min(end, s.today) if start <= s.today else end


# ---------------------------------------------------------------- endpoints
# Not /healthz: Cloud Run's front end reserves URL paths ending in "z" and returns its own 404.
@app.get("/health", tags=["ops"])
def health(svc: Services = Depends(services)):
    return {"ok": True, "model": svc.settings.gemini_model, "dataset": svc.settings.dataset, "today": svc.settings.today}


@app.get("/transactions", tags=["data"])
def transactions(month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"), category: Optional[str] = None,
                 limit: int = Query(100, ge=1, le=500), svc: Services = Depends(services)):
    start, end = _range(month, svc.settings)
    return {"start": start, "end": end, "items": svc.warehouse.transactions(start, end, category, limit)}


@app.get("/analytics/categories", tags=["analytics"])
def categories(month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"), svc: Services = Depends(services)):
    start, end = _range(month, svc.settings)
    return {"start": start, "end": end, "items": svc.warehouse.spend_by_category(start, end),
            "top_merchants": svc.warehouse.top_merchants(start, end)}


@app.get("/analytics/monthly", tags=["analytics"])
def monthly(category: Optional[str] = None, svc: Services = Depends(services)):
    start, end = resolve_period("last_12_months", svc.settings.today)
    return {"start": start, "end": end, "category": category, "items": svc.warehouse.monthly_trend(start, end, category)}


@app.get("/budgets/status", tags=["analytics"])
def budgets(svc: Services = Depends(services)):
    return {"items": svc.warehouse.budget_status()}


@app.get("/alerts", tags=["analytics"])
def alerts(limit: int = Query(20, ge=1, le=100), svc: Services = Depends(services)):
    return {"items": svc.warehouse.alerts(limit)}


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=10)


@app.post("/chat", tags=["agent"])
def chat(req: ChatRequest, svc: Services = Depends(services)):
    out = svc.advisor.invoke({"question": req.message, "history": [t.model_dump() for t in req.history]})
    return {"answer": out["answer"], "intent": out["intent"], "period": out.get("period"),
            "data": out.get("tool_results", {})}


@app.post("/categorize", tags=["agent"])
def categorize(limit: int = Query(200, ge=1, le=1000), svc: Services = Depends(services)):
    """Categorize uncategorized transactions with Gemini. Called by the daily job and from the UI."""
    return categorize_pending(svc.llm, svc.warehouse, limit)


@app.get("/categorize/accuracy", tags=["agent"])
def accuracy(svc: Services = Depends(services)):
    """Gemini's categories vs. the synthetic ground truth."""
    return svc.warehouse.categorization_accuracy()


@app.post("/receipts", tags=["agent"])
async def receipts(file: UploadFile = File(...), svc: Services = Depends(services)):
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, f"Upload a receipt image ({', '.join(sorted(ALLOWED_IMAGE_TYPES))})")
    data = await file.read(MAX_RECEIPT_BYTES + 1)
    if len(data) > MAX_RECEIPT_BYTES:
        raise HTTPException(413, "Receipt image must be 8 MB or smaller")
    ext = content_type.split("/")[1].replace("jpeg", "jpg")
    uri = svc.upload_receipt(data, content_type, f"{uuid.uuid4().hex}.{ext}")
    return process_receipt(svc.llm, svc.warehouse, image=data, mime_type=content_type, gcs_uri=uri,
                           user_id=svc.settings.user_id, model_name=svc.settings.gemini_model)
