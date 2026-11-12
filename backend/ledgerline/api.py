"""HTTP API used by the reviewer UI.  Run: uvicorn ledgerline.api:app --reload"""
from __future__ import annotations

import json

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db
from .config import USD_TO_INR, get_settings
from .evidence import (
    build_invoice_evidence,
    build_review_details,
    review_priority,
)
from .pipeline import process_document
from .reference import load_reference
from .validation import find_duplicate_records

app = FastAPI(title="Ledgerline API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_conn():
    conn = db.connect(get_settings().db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_org(x_org_id: str = Header(default="meridian")) -> str:
    return x_org_id


class DecisionRequest(BaseModel):
    user_id: str
    note: str = ""


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/invoices")
async def upload_invoice(file: UploadFile, org_id: str = Depends(get_org), conn=Depends(get_conn)):
    raw_text = (await file.read()).decode("utf-8")
    document_id = (file.filename or "upload").rsplit(".", 1)[0]
    invoice = process_document(conn, load_reference(), raw_text, document_id, org_id=org_id, filename=file.filename)
    return _with_evidence(invoice, conn)


@app.get("/api/invoices")
def list_invoices(
    status: str = "all",
    limit: int = 300,
    offset: int = 0,
    org_id: str = Depends(get_org),
    conn=Depends(get_conn),
):
    allowed_statuses = {"all", "needs_review", "ready_for_approval", "approved", "rejected"}
    if status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Invalid invoice queue status")
    if not 1 <= limit <= 1000 or offset < 0:
        raise HTTPException(status_code=422, detail="Invalid invoice queue pagination")
    rows = conn.execute(
        "SELECT id, document_id, supplier_name, invoice_number, invoice_date, currency, total_paise, status, "
        "needs_review, review_reasons_json, created_at FROM invoices WHERE org_id = ?",
        (org_id,),
    ).fetchall()
    results = []
    for row in rows:
        invoice = dict(row)
        if status != "all" and invoice["status"] != status:
            continue
        reasons = json.loads(invoice.pop("review_reasons_json") or "[]")
        rank, priority = review_priority(invoice["status"], reasons)
        invoice["total"] = db.from_paise(invoice.pop("total_paise"))
        invoice["review_reasons"] = reasons
        invoice["priority"] = priority
        invoice["_priority_rank"] = rank
        results.append(invoice)
    results.sort(key=lambda invoice: (invoice["_priority_rank"], invoice["created_at"], invoice["id"]))
    page = results[offset : offset + limit]
    for invoice in page:
        invoice.pop("_priority_rank")
        invoice.pop("created_at")
    return page


@app.get("/api/invoices/{invoice_id}")
def get_invoice(invoice_id: int, conn=Depends(get_conn)):
    invoice = db.get_invoice(conn, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return _with_evidence(invoice, conn)


@app.post("/api/invoices/{invoice_id}/approve")
def approve_invoice(invoice_id: int, body: DecisionRequest, conn=Depends(get_conn)):
    try:
        conn.execute("BEGIN IMMEDIATE")
        invoice = db.get_invoice(conn, invoice_id)
        if invoice is None:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if invoice["status"] in {"approved", "rejected"}:
            approvals = conn.execute(
                "SELECT COUNT(*) FROM approvals WHERE invoice_id = ?", (invoice_id,)
            ).fetchone()[0]
            conn.commit()
            return {
                "id": invoice_id,
                "approvals": approvals,
                "required_approvals": invoice["required_approvals"],
                "status": invoice["status"],
            }
        reasons = invoice.get("review_reasons") or []
        user_id = body.user_id.strip()
        if not user_id:
            raise HTTPException(status_code=422, detail="Approver identity is required")
        if (
            invoice["document_type"] == "credit_note"
            or "duplicate" in reasons
            or "processing_error" in reasons
            or invoice["total"] is None
        ):
            raise HTTPException(status_code=409, detail="This document cannot be approved")
        if invoice["needs_review"] and not body.note.strip():
            raise HTTPException(status_code=422, detail="An approval note is required for reviewed documents")
        conn.execute(
            "INSERT OR IGNORE INTO approvals (invoice_id, user_id, note) VALUES (?, ?, ?)",
            (invoice_id, user_id, body.note),
        )
        approvals = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM approvals WHERE invoice_id = ?", (invoice_id,)
        ).fetchone()[0]
        status = invoice["status"]
        if approvals >= invoice["required_approvals"]:
            updated = conn.execute(
                "UPDATE invoices SET status = 'approved' WHERE id = ? "
                "AND status IN ('ready_for_approval', 'needs_review')",
                (invoice_id,),
            ).rowcount
            if updated:
                conn.execute(
                    "INSERT INTO payments (invoice_id, amount_paise) VALUES (?, ?)",
                    (invoice_id, db.get_total_paise(conn, invoice_id)),
                )
            status = "approved"
        conn.commit()
        return {
            "id": invoice_id,
            "approvals": approvals,
            "required_approvals": invoice["required_approvals"],
            "status": status,
        }
    except Exception:
        conn.rollback()
        raise


@app.post("/api/invoices/{invoice_id}/reject")
def reject_invoice(invoice_id: int, body: DecisionRequest, conn=Depends(get_conn)):
    try:
        conn.execute("BEGIN IMMEDIATE")
        invoice = db.get_invoice(conn, invoice_id)
        if invoice is None:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if not body.user_id.strip():
            raise HTTPException(status_code=422, detail="Reviewer identity is required")
        if invoice["status"] == "approved":
            raise HTTPException(status_code=409, detail="An approved invoice cannot be rejected")
        existing = conn.execute(
            "SELECT user_id, note FROM rejections WHERE invoice_id = ?", (invoice_id,)
        ).fetchone()
        if invoice["status"] == "rejected" or existing:
            conn.commit()
            return {
                "id": invoice_id,
                "status": "rejected",
                "rejected_by": existing["user_id"] if existing else None,
            }
        user_id = body.user_id.strip()
        conn.execute(
            "INSERT INTO rejections (invoice_id, user_id, note) VALUES (?, ?, ?)",
            (invoice_id, user_id, body.note),
        )
        conn.execute(
            "UPDATE invoices SET status = 'rejected' WHERE id = ? "
            "AND status IN ('ready_for_approval', 'needs_review')",
            (invoice_id,),
        )
        conn.commit()
        return {"id": invoice_id, "status": "rejected", "rejected_by": user_id}
    except Exception:
        conn.rollback()
        raise


def _with_evidence(invoice: dict, conn) -> dict:
    evidence = build_invoice_evidence(invoice)
    invoice["evidence"] = evidence
    duplicate_matches = []
    if "duplicate" in invoice["review_reasons"]:
        duplicate_matches = find_duplicate_records(
            conn,
            load_reference(),
            document_type=invoice["document_type"],
            supplier_gstin=invoice["supplier_gstin"],
            supplier_name=invoice["supplier_name"],
            currency=invoice["currency"],
            invoice_number=invoice["invoice_number"],
            invoice_date=invoice["invoice_date"],
            exclude_invoice_id=invoice["id"],
        )
    invoice["review_details"] = build_review_details(invoice, evidence, duplicate_matches)
    _, invoice["priority"] = review_priority(invoice["status"], invoice["review_reasons"])
    invoice["approval_count"] = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM approvals WHERE invoice_id = ?",
        (invoice["id"],),
    ).fetchone()[0]
    return invoice


@app.get("/api/stats")
def stats(org_id: str = Depends(get_org), conn=Depends(get_conn)):
    """Feeds the cost dashboard."""
    row = conn.execute(
        "SELECT COUNT(DISTINCT c.invoice_id) AS invoices, COALESCE(SUM(c.cost_usd), 0) AS cost_usd, "
        "SUM(CASE WHEN c.cost_usd IS NULL THEN 1 ELSE 0 END) AS unpriced_calls "
        "FROM llm_calls c JOIN invoices i ON i.id = c.invoice_id WHERE i.org_id = ?",
        (org_id,),
    ).fetchone()
    total_inr = row["cost_usd"] * USD_TO_INR
    unpriced_calls = row["unpriced_calls"] or 0
    return {
        "invoices_processed": row["invoices"],
        "llm_cost_inr": round(total_inr, 2) if not unpriced_calls else None,
        "unpriced_calls": unpriced_calls,
        "avg_llm_cost_per_invoice_inr": (
            round(total_inr / row["invoices"], 4)
            if row["invoices"] and not unpriced_calls
            else None
        ),
    }
