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

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from smartspend_agent import Settings, build_advisor
from smartspend_agent.categorizer import categorize_pending
from smartspend_agent.graph import resolve_period
from smartspend_agent.categories import Category
from smartspend_agent.own_data import (add_manual, find_account, import_statement, preview_statement,
                                       transaction_from_receipt)
from smartspend_agent.receipts import process_receipt
from smartspend_agent.statements import StatementRow, parse_statement
from smartspend_agent.warehouse import now_utc

log = logging.getLogger("smartspend")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

MAX_RECEIPT_BYTES = 8 * 1024 * 1024
MAX_STATEMENT_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
STATEMENT_TYPES = {"csv": "text/csv", "pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                   "png": "image/png"}


@dataclass
class Services:
    settings: Settings
    llm: Any
    warehouse: Any
    advisor: Any
    upload: Any  # (bytes, content_type, object path) -> gs:// uri


def build_services() -> Services:
    from google.cloud import storage

    from smartspend_agent.llm import Gemini
    from smartspend_agent.warehouse import BigQueryWarehouse

    s = Settings.from_env()
    llm = Gemini(s.project, s.gemini_location, s.gemini_model)
    wh = BigQueryWarehouse(s.project, s.dataset, s.user_id)
    bucket = storage.Client(project=s.project).bucket(s.receipts_bucket)

    def upload(data: bytes, content_type: str, path: str) -> str:
        blob = bucket.blob(path)
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
                 account_id: Optional[str] = None, limit: int = Query(100, ge=1, le=500),
                 svc: Services = Depends(services)):
    start, end = _range(month, svc.settings)
    return {"start": start, "end": end,
            "items": svc.warehouse.transactions(start, end, category, limit, account_id)}


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
    uri = svc.upload(data, content_type, f"uploads/{svc.settings.user_id}/{uuid.uuid4().hex}.{ext}")
    return process_receipt(svc.llm, svc.warehouse, image=data, mime_type=content_type, gcs_uri=uri,
                           user_id=svc.settings.user_id, model_name=svc.settings.gemini_model)


# ------------------------------------------------------- your own data
def _account(svc: Services, account_id: str) -> dict:
    account = find_account(svc.warehouse, account_id)
    if not account:
        raise HTTPException(404, f"Unknown account {account_id}")
    return account


@app.get("/accounts", tags=["your data"])
def list_accounts(svc: Services = Depends(services)):
    return {"items": svc.warehouse.accounts()}


class NewAccount(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: str = Field(pattern="^(checking|savings|credit_card|cash)$")
    institution: Optional[str] = Field(None, max_length=80)
    last4: Optional[str] = Field(None, pattern=r"^\d{4}$")


@app.post("/accounts", tags=["your data"], status_code=201)
def create_account(body: NewAccount, svc: Services = Depends(services)):
    row = {"account_id": "acct_" + uuid.uuid4().hex[:10], "user_id": svc.settings.user_id, **body.model_dump(),
           "is_demo": False, "created_at": now_utc()}
    svc.warehouse.create_account(row)
    return row


class NewTransaction(BaseModel):
    account_id: str
    txn_date: date
    description: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=1_000_000)
    direction: str = Field("debit", pattern="^(debit|credit)$")
    category: Optional[Category] = Field(None, description="Leave empty and Gemini picks one")


@app.post("/transactions", tags=["your data"], status_code=201)
def create_transaction(body: NewTransaction, svc: Services = Depends(services)):
    if body.txn_date > svc.settings.today:
        raise HTTPException(422, "The date can't be in the future")
    return add_manual(svc.llm, svc.warehouse, user_id=svc.settings.user_id, account=_account(svc, body.account_id),
                      txn_date=body.txn_date, description=body.description, amount=body.amount,
                      direction=body.direction, category=body.category.value if body.category else None)


class CategoryChange(BaseModel):
    category: Category


@app.patch("/transactions/{transaction_id}/category", tags=["your data"])
def change_category(transaction_id: str, body: CategoryChange, svc: Services = Depends(services)):
    if not svc.warehouse.set_category(transaction_id, body.category.value):
        raise HTTPException(404, "Transaction not found")
    return {"transaction_id": transaction_id, "category": body.category.value, "category_source": "user"}


def _statement_type(file: UploadFile) -> tuple[str, str]:
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in STATEMENT_TYPES:
        raise HTTPException(415, "Upload a CSV or PDF statement (or a photo of one)")
    return ("csv" if ext == "csv" else "pdf" if ext == "pdf" else "image"), STATEMENT_TYPES[ext]


@app.post("/statements/preview", tags=["your data"])
async def statement_preview(account_id: str = Form(...), file: UploadFile = File(...),
                            svc: Services = Depends(services)):
    """Read a statement and show the rows. Nothing is saved to BigQuery until /statements/import."""
    account = _account(svc, account_id)
    fmt, mime = _statement_type(file)
    data = await file.read(MAX_STATEMENT_BYTES + 1)
    if len(data) > MAX_STATEMENT_BYTES:
        raise HTTPException(413, "Statement must be 10 MB or smaller")
    uri = svc.upload(data, mime, f"statements/{svc.settings.user_id}/{uuid.uuid4().hex}-{file.filename}"[:900])
    parsed = parse_statement(svc.llm, data, mime, svc.settings.gemini_model)
    if not parsed.rows:
        raise HTTPException(422, "No transactions found in that file")
    warnings = list(parsed.warnings)
    if parsed.account_last4 and account.get("last4") and parsed.account_last4 != account["last4"]:
        warnings.append(f"The statement is for an account ending {parsed.account_last4}, "
                        f"but {account['name']} ends {account['last4']}.")
    return {
        "account_id": account_id, "filename": file.filename, "format": fmt, "gcs_uri": uri,
        "parser": parsed.parser, "warnings": warnings,
        "rows": preview_statement(svc.warehouse, user_id=svc.settings.user_id, account_id=account_id,
                                  rows=parsed.rows),
    }


class StatementImport(BaseModel):
    account_id: str
    filename: str = Field(max_length=200)
    format: str = Field(pattern="^(csv|pdf|image)$")
    gcs_uri: str
    parser: str = Field(max_length=80)
    rows_parsed: int = Field(ge=0)
    rows: list[StatementRow] = Field(max_length=5000, description="The rows the user kept ticked")


@app.post("/statements/import", tags=["your data"])
def statement_import(body: StatementImport, svc: Services = Depends(services)):
    expected = f"gs://{svc.settings.receipts_bucket}/statements/{svc.settings.user_id}/"
    if svc.settings.receipts_bucket and not body.gcs_uri.startswith(expected):
        raise HTTPException(422, "Unknown statement file")
    return import_statement(svc.llm, svc.warehouse, user_id=svc.settings.user_id,
                            account=_account(svc, body.account_id), rows=body.rows, filename=body.filename,
                            gcs_uri=body.gcs_uri, fmt=body.format, parser=body.parser,
                            rows_parsed=max(body.rows_parsed, len(body.rows)))


@app.get("/imports", tags=["your data"])
def list_imports(svc: Services = Depends(services)):
    return {"items": svc.warehouse.imports()}


@app.post("/imports/{import_id}/undo", tags=["your data"])
def undo_import(import_id: str, svc: Services = Depends(services)):
    return {"import_id": import_id, "deleted": svc.warehouse.undo_import(import_id)}


class ReceiptToTransaction(BaseModel):
    account_id: str


@app.post("/receipts/{receipt_id}/transaction", tags=["your data"], status_code=201)
def receipt_transaction(receipt_id: str, body: ReceiptToTransaction, svc: Services = Depends(services)):
    receipt = svc.warehouse.receipt(receipt_id)
    if not receipt:
        raise HTTPException(404, "Receipt not found")
    if receipt.get("matched_transaction_id"):
        raise HTTPException(409, "This receipt is already matched to a transaction")
    if not receipt.get("receipt_date") or receipt.get("total") is None:
        raise HTTPException(422, "The receipt's date or total couldn't be read")
    return transaction_from_receipt(svc.warehouse, user_id=svc.settings.user_id, receipt=receipt,
                                    account=_account(svc, body.account_id))
