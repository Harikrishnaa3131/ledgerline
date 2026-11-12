"""Process one document end to end: extract -> normalise -> check -> route -> persist."""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict
from decimal import Decimal

from . import db
from .extraction import ExtractionError, extract
from .llm import ProviderError
from .llm.pricing import cost_usd
from .models import Invoice, LineItem
from .parsing import parse_amount, parse_date
from .reference import ReferenceData
from .validation import find_vendor, run_checks

HIGH_VALUE_THRESHOLD = Decimal("500000.00")


def normalize(data: dict, ref: ReferenceData | None = None, raw_text: str = "") -> Invoice:
    currency = str(data.get("currency") or "").upper()
    vendor = (
        find_vendor(ref, data.get("supplier_gstin"), data.get("supplier_name"), currency)
        if ref
        else None
    )
    items = [
        LineItem(
            description=str(item.get("description", "")),
            quantity=parse_amount(item.get("quantity")),
            unit_price=parse_amount(item.get("unit_price")),
            amount=parse_amount(item.get("amount")) or Decimal("0.00"),
        )
        for item in data.get("line_items") or []
    ]
    bank_account, ifsc = extract_bank_details(raw_text)
    return Invoice(
        document_type=str(data.get("document_type") or "").lower(),
        supplier_name=data.get("supplier_name"),
        supplier_gstin=data.get("supplier_gstin"),
        invoice_number=data.get("invoice_number"),
        invoice_date=parse_date(
            data.get("invoice_date"),
            dayfirst=not bool(vendor and vendor.get("country") == "US"),
        ),
        currency=currency,
        subtotal=parse_amount(data.get("subtotal")),
        cgst=parse_amount(data.get("cgst")) or Decimal("0.00"),
        sgst=parse_amount(data.get("sgst")) or Decimal("0.00"),
        igst=parse_amount(data.get("igst")) or Decimal("0.00"),
        round_off=parse_amount(data.get("round_off")) or Decimal("0.00"),
        total=parse_amount(data.get("total")),
        bank_account=bank_account,
        ifsc=ifsc,
        po_number=data.get("po_number"),
        notes=data.get("notes"),
        line_items=items,
    )


def process_document(
    conn: sqlite3.Connection,
    ref: ReferenceData,
    raw_text: str,
    document_id: str,
    org_id: str = "meridian",
    filename: str | None = None,
) -> dict:
    responses = []
    try:
        data, responses = extract(raw_text, ref)
        inv = normalize(data, ref, raw_text)
        if inv.document_type not in {"invoice", "credit_note"}:
            raise ValueError("unsupported document type")
        if not inv.invoice_number or not inv.invoice_date or not inv.currency or inv.total is None:
            raise ValueError("required invoice fields are missing")
    except (ExtractionError, ProviderError, ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        if isinstance(exc, ExtractionError):
            responses = exc.responses
        inv = _processing_error_invoice()
        review_reasons = ["processing_error"]
        warnings = [f"processing_error: {type(exc).__name__}"]
        processing_failed = True
    else:
        processing_failed = False

    conn.execute("BEGIN IMMEDIATE")
    try:
        if not processing_failed:
            review_reasons = run_checks(conn, ref, inv, raw_text)
        warnings = list(review_reasons) if not processing_failed else warnings
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, sqlite3.Error) as exc:
        conn.rollback()
        return record_processing_error(conn, document_id, filename, exc, raw_text=raw_text, org_id=org_id)

    try:
        needs_review = bool(review_reasons)
        required_approvals = _required_approvals(inv)
        status = "needs_review" if needs_review else "ready_for_approval"
        cur = conn.execute(
            """INSERT INTO invoices (org_id, document_id, filename, raw_text, document_type, supplier_name,
                   supplier_gstin, invoice_number, invoice_date, currency, subtotal, cgst, sgst, igst, round_off,
                   total, subtotal_paise, cgst_paise, sgst_paise, igst_paise, round_off_paise, total_paise,
                   bank_account, ifsc, po_number, notes, line_items_json, warnings_json, needs_review,
                   review_reasons_json, required_approvals, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                org_id,
                document_id,
                filename,
                raw_text,
                inv.document_type,
                inv.supplier_name,
                inv.supplier_gstin,
                inv.invoice_number,
                inv.invoice_date.isoformat() if inv.invoice_date else None,
                inv.currency,
                None,
                None,
                None,
                None,
                None,
                None,
                db.to_paise(inv.subtotal),
                db.to_paise(inv.cgst),
                db.to_paise(inv.sgst),
                db.to_paise(inv.igst),
                db.to_paise(inv.round_off),
                db.to_paise(inv.total),
                inv.bank_account,
                inv.ifsc,
                inv.po_number,
                inv.notes,
                json.dumps([_json_line_item(asdict(item)) for item in inv.line_items]),
                json.dumps(warnings),
                int(needs_review),
                json.dumps(review_reasons),
                required_approvals,
                status,
            ),
        )
        invoice_id = cur.lastrowid
        for response in responses:
            conn.execute(
                "INSERT INTO llm_calls (invoice_id, document_id, model, input_tokens, output_tokens, cost_usd, "
                "latency_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    invoice_id,
                    document_id,
                    response.model,
                    response.input_tokens,
                    response.output_tokens,
                    cost_usd(response.model, response.input_tokens, response.output_tokens),
                    response.latency_ms,
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return db.get_invoice(conn, invoice_id)


def record_processing_error(
    conn: sqlite3.Connection,
    document_id: str,
    filename: str | None,
    error: Exception,
    raw_text: str = "",
    org_id: str = "meridian",
) -> dict:
    cur = conn.execute(
        """INSERT INTO invoices (org_id, document_id, filename, raw_text, document_type, currency,
               warnings_json, needs_review, review_reasons_json, required_approvals, status)
           VALUES (?, ?, ?, ?, 'invoice', 'INR', ?, 1, ?, 1, 'needs_review')""",
        (
            org_id,
            document_id,
            filename,
            raw_text,
            json.dumps([f"processing_error: {type(error).__name__}"]),
            json.dumps(["processing_error"]),
        ),
    )
    conn.commit()
    return db.get_invoice(conn, cur.lastrowid)


def extract_bank_details(raw_text: str) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        payload = None
    account, ifsc = _bank_details_from_json(payload)
    if account or ifsc:
        return account, ifsc
    account_match = re.search(
        r"(?i)(?:a/c|account|acct)(?:\s*(?:no\.?|number|#))?\s*[:#-]?\s*"
        r"([0-9][0-9 -]{5,23})",
        raw_text,
    )
    if account_match is None:
        account_match = re.search(
            r'(?i)"(?:bank_account|account_number|acct_no)"\s*:\s*"?([0-9]{6,18})',
            raw_text,
        )
    account = re.sub(r"\D", "", account_match.group(1)) if account_match else None
    ifsc_match = re.search(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", raw_text, re.IGNORECASE)
    return account, ifsc_match.group(0).upper() if ifsc_match else None


def _bank_details_from_json(payload: object) -> tuple[str | None, str | None]:
    if isinstance(payload, dict):
        account_keys = {"bankaccount", "accountnumber", "accountno", "acctno", "accno", "accnum"}
        account = ifsc = None
        for key, value in payload.items():
            normalized_key = re.sub(r"[^a-z]", "", str(key).lower())
            if normalized_key in account_keys and isinstance(value, (str, int)):
                digits = re.sub(r"\D", "", str(value))
                if 6 <= len(digits) <= 18:
                    account = digits
            elif normalized_key in {"ifsc", "ifscode"} and isinstance(value, str):
                ifsc = value.strip().upper()
            nested_account, nested_ifsc = _bank_details_from_json(value)
            account = account or nested_account
            ifsc = ifsc or nested_ifsc
        return account, ifsc
    if isinstance(payload, list):
        for item in payload:
            account, ifsc = _bank_details_from_json(item)
            if account or ifsc:
                return account, ifsc
    return None, None


def _processing_error_invoice() -> Invoice:
    return Invoice(
        document_type="invoice",
        supplier_name=None,
        supplier_gstin=None,
        invoice_number=None,
        invoice_date=None,
        currency="INR",
        subtotal=None,
        cgst=Decimal(0),
        sgst=Decimal(0),
        igst=Decimal(0),
        round_off=Decimal(0),
        total=None,
        bank_account=None,
        ifsc=None,
        po_number=None,
        notes=None,
    )


def _required_approvals(inv: Invoice) -> int:
    if inv.document_type == "credit_note":
        return 0
    if inv.currency.upper() != "INR" or (inv.total is not None and inv.total >= HIGH_VALUE_THRESHOLD):
        return 2
    return 1


def _json_line_item(item: dict) -> dict:
    return {key: str(value) if isinstance(value, Decimal) else value for key, value in item.items()}
