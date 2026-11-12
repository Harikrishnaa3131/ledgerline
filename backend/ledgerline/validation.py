"""Deterministic AP policy checks used to route documents."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from datetime import date
from decimal import Decimal

from .models import Invoice
from .reference import ReferenceData

GSTIN_PATTERN = re.compile(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]")
GSTIN_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ACCOUNT_NUMBER_PATTERN = re.compile(r"[^0-9]")
INVOICE_NUMBER_PATTERN = re.compile(r"[^A-Z0-9]")
SUSPICIOUS_PATTERNS = (
    re.compile(r"\b(?:for|to)\s+(?:the\s+)?(?:ai|llm|model|assistant|automated system|ledgerline)\b", re.IGNORECASE),
    re.compile(r"\b(?:ai|llm)\s+assistants?\b|\bautomated invoice processing\b", re.IGNORECASE),
    re.compile(
        r"\b(?:set|mark|route|return|leave)\b.{0,60}\b"
        r"(?:requires_review|review_reasons|approved|approval|ready)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:ignore|disregard|override|bypass|skip)\b.{0,100}\b(?:instructions?|policy|checks?|rules?|review|approval)\b", re.IGNORECASE),
    re.compile(r"<\s*/?\s*[a-z][a-z0-9]*(?:\s+[^<>]*|/?)>", re.IGNORECASE),
)


def gstin_checksum(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = GSTIN_ALPHABET.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return GSTIN_ALPHABET[(36 - total % 36) % 36]


def is_valid_gstin(gstin: str | None) -> bool:
    """Validate a GSTIN's format and checksum."""
    if not gstin:
        return False
    value = gstin.strip().upper()
    return bool(GSTIN_PATTERN.fullmatch(value)) and gstin_checksum(value[:14]) == value[-1]


def normalize_invoice_number(invoice_number: str | None) -> str:
    return INVOICE_NUMBER_PATTERN.sub("", (invoice_number or "").upper())


def normalize_foreign_name(name: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", name or "")
    return INVOICE_NUMBER_PATTERN.sub("", normalized.upper())


def find_vendor(
    ref: ReferenceData,
    supplier_gstin: str | None,
    supplier_name: str | None,
    currency: str,
) -> dict | None:
    if currency.upper() == "INR":
        if not supplier_gstin:
            return None
        gstin = supplier_gstin.strip().upper()
        return next((v for v in ref.vendors if (v.get("gstin") or "").upper() == gstin), None)
    normalized_name = normalize_foreign_name(supplier_name)
    if not normalized_name:
        return None
    for vendor in ref.vendors:
        if vendor.get("country") != "IN" and normalize_foreign_name(vendor.get("legal_name")) == normalized_name:
            return vendor
    return None


def check_vendor(vendor: dict | None) -> list[str]:
    return [] if vendor else ["vendor_unknown"]


def check_gstin(inv: Invoice) -> list[str]:
    if inv.currency == "INR" and not is_valid_gstin(inv.supplier_gstin):
        return ["gstin_invalid"]
    return []


def check_tax_type(inv: Invoice, buyer_state_code: str = "27") -> list[str]:
    if not inv.supplier_gstin:
        return []
    intra_state = inv.supplier_gstin.strip().upper()[:2] == buyer_state_code
    if (intra_state and inv.igst > 0) or (
        not intra_state and (inv.cgst > 0 or inv.sgst > 0)
    ):
        return ["tax_type_mismatch"]
    return []


def check_totals(inv: Invoice) -> list[str]:
    if inv.total is None:
        return []
    tolerance = Decimal("1.00")
    line_sum = sum((Decimal(str(item.amount)) for item in inv.line_items), Decimal(0))
    if inv.subtotal is not None and abs(line_sum - Decimal(str(inv.subtotal))) > tolerance:
        return ["totals_mismatch"]
    for item in inv.line_items:
        if item.quantity is not None and item.unit_price is not None:
            line_total = Decimal(str(item.quantity)) * Decimal(str(item.unit_price))
            if abs(line_total - Decimal(str(item.amount))) > tolerance:
                return ["totals_mismatch"]
    computed = line_sum + sum(
        (Decimal(str(amount)) for amount in (inv.cgst, inv.sgst, inv.igst, inv.round_off)),
        Decimal(0),
    )
    return [] if abs(computed - Decimal(str(inv.total))) <= tolerance else ["totals_mismatch"]


def check_duplicate(conn: sqlite3.Connection, ref: ReferenceData, inv: Invoice) -> list[str]:
    if inv.document_type != "invoice" or not inv.invoice_date or not inv.invoice_number:
        return []
    supplier_key = _supplier_key(inv.supplier_gstin, inv.supplier_name, inv.currency)
    if not supplier_key[1]:
        return []
    normalized_number = normalize_invoice_number(inv.invoice_number)
    fiscal_year = _fiscal_year(inv.invoice_date)
    for paid in ref.paid_invoices:
        paid_key = _supplier_key(paid.get("supplier_gstin"), paid.get("supplier_name"), inv.currency)
        if (
            paid_key == supplier_key
            and normalize_invoice_number(paid.get("invoice_number")) == normalized_number
            and _date_fiscal_year(paid.get("invoice_date")) == fiscal_year
        ):
            return ["duplicate"]
    rows = conn.execute(
        "SELECT document_type, supplier_name, supplier_gstin, invoice_number, invoice_date FROM invoices"
    ).fetchall()
    for row in rows:
        if (
            row["document_type"] == "invoice"
            and _supplier_key(row["supplier_gstin"], row["supplier_name"], inv.currency) == supplier_key
            and normalize_invoice_number(row["invoice_number"]) == normalized_number
            and _date_fiscal_year(row["invoice_date"]) == fiscal_year
        ):
            return ["duplicate"]
    return []


def check_bank_details(inv: Invoice, vendor: dict | None) -> list[str]:
    if not vendor:
        return []
    account_changed = bool(inv.bank_account and vendor.get("bank_account")) and (
        ACCOUNT_NUMBER_PATTERN.sub("", inv.bank_account)
        != ACCOUNT_NUMBER_PATTERN.sub("", vendor["bank_account"])
    )
    ifsc_changed = bool(inv.ifsc and vendor.get("ifsc")) and (
        inv.ifsc.strip().upper() != vendor["ifsc"].strip().upper()
    )
    return ["bank_details_changed"] if account_changed or ifsc_changed else []


def check_vendor_new(inv: Invoice, vendor: dict | None) -> list[str]:
    if not inv.invoice_date or not vendor or not vendor.get("onboarded_on"):
        return []
    onboarded = date.fromisoformat(vendor["onboarded_on"])
    age_days = (inv.invoice_date - onboarded).days
    return ["vendor_new"] if 0 <= age_days < 90 else []


def check_suspicious_content(raw_text: str) -> list[str]:
    if any(pattern.search(raw_text) for pattern in SUSPICIOUS_PATTERNS):
        return ["suspicious_content"]
    return []


def check_buyer_gstin(raw_text: str, ref: ReferenceData) -> list[str]:
    buyer_gstin = (ref.buyer.get("gstin") or "").upper()
    if not buyer_gstin:
        return []
    document_gstin = _extract_buyer_gstin(raw_text)
    if document_gstin and document_gstin != buyer_gstin:
        return ["buyer_gstin_mismatch"] if os.getenv("LEDGERLINE_FLAG_BUYER_GSTIN_MISMATCH") == "1" else []
    return []


def run_checks(conn: sqlite3.Connection, ref: ReferenceData, inv: Invoice, raw_text: str = "") -> list[str]:
    vendor = find_vendor(ref, inv.supplier_gstin, inv.supplier_name, inv.currency)
    buyer_state = str(ref.buyer.get("state_code") or ref.buyer.get("gstin", "")[:2])
    return (
        (["credit_note"] if inv.document_type == "credit_note" else [])
        + check_gstin(inv)
        + check_vendor(vendor)
        + check_tax_type(inv, buyer_state)
        + check_totals(inv)
        + check_duplicate(conn, ref, inv)
        + check_bank_details(inv, vendor)
        + check_vendor_new(inv, vendor)
        + (["foreign_currency"] if inv.currency.upper() != "INR" else [])
        + check_suspicious_content(raw_text)
        + check_buyer_gstin(raw_text, ref)
    )


def _supplier_key(gstin: str | None, supplier_name: str | None, currency: str) -> tuple[str, str]:
    if currency.upper() == "INR":
        return "domestic", (gstin or "").strip().upper()
    return "foreign", normalize_foreign_name(supplier_name)


def _fiscal_year(invoice_date: date) -> int:
    return invoice_date.year if invoice_date.month >= 4 else invoice_date.year - 1


def _date_fiscal_year(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return _fiscal_year(date.fromisoformat(value[:10]))
    except ValueError:
        return None


def _extract_buyer_gstin(raw_text: str) -> str | None:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        buyer = payload.get("BuyerDtls") or payload.get("buyer") or {}
        if isinstance(buyer, dict):
            value = buyer.get("Gstin") or buyer.get("gstin")
            if value:
                return str(value).strip().upper()
    match = re.search(
        r"(?:buyer|bill\s*to|recipient).{0,120}?(?:GSTIN(?:/UIN)?|GSTIN)\s*[:#]?\s*([0-9A-Z]{15})",
        raw_text,
        re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).upper() if match else None
