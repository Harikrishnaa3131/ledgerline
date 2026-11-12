"""HTTP API used by the reviewer UI.  Run: uvicorn ledgerline.api:app --reload"""
from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db
from .config import USD_TO_INR, get_settings
from .pipeline import process_document
from .reference import load_reference

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
    return process_document(conn, load_reference(), raw_text, document_id, org_id=org_id, filename=file.filename)


@app.get("/api/invoices")
def list_invoices(org_id: str = Depends(get_org), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, document_id, supplier_name, invoice_number, invoice_date, currency, total_paise, status, "
        "needs_review FROM invoices WHERE org_id = ? ORDER BY id DESC",
        (org_id,),
    ).fetchall()
    results = []
    for row in rows:
        invoice = dict(row)
        invoice["total"] = db.from_paise(invoice.pop("total_paise"))
        results.append(invoice)
    return results


@app.get("/api/invoices/{invoice_id}")
def get_invoice(invoice_id: int, conn=Depends(get_conn)):
    invoice = db.get_invoice(conn, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


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
        if not body.user_id.strip():
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
            (invoice_id, body.user_id, body.note),
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
    conn.execute("UPDATE invoices SET status = 'rejected' WHERE id = ?", (invoice_id,))
    conn.commit()
    return {"id": invoice_id, "status": "rejected"}


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
