"""Exact source spans and reviewer-facing explanations for invoice decisions."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .validation import SUSPICIOUS_PATTERNS

MONEY_FIELDS = {"subtotal", "cgst", "sgst", "igst", "round_off", "total"}
COMPACT_FIELDS = {
    "supplier_name",
    "supplier_gstin",
    "invoice_number",
    "bank_account",
    "ifsc",
    "po_number",
}

REVIEW_REASON_DETAILS = {
    "bank_details_changed": (
        "Bank details differ from the matched vendor record.",
        ["bank_account", "ifsc"],
    ),
    "credit_note": (
        "Credit notes reduce the balance owed and cannot be approved for payment.",
        ["document_type", "invoice_number"],
    ),
    "duplicate": (
        "The supplier key, normalized invoice number and financial year match a paid or earlier invoice.",
        ["supplier_gstin", "supplier_name", "invoice_number", "invoice_date"],
    ),
    "foreign_currency": (
        "The invoice is not denominated in INR and requires the policy's additional approval.",
        ["currency", "total"],
    ),
    "gstin_invalid": (
        "The domestic supplier GSTIN is missing, malformed or fails its checksum.",
        ["supplier_gstin"],
    ),
    "processing_error": (
        "Ledgerline could not process this document reliably; do not approve it automatically.",
        [],
    ),
    "suspicious_content": (
        "The document contains text addressed to an automated system or embedded markup.",
        [],
    ),
    "tax_type_mismatch": (
        "The supplier and buyer state codes do not agree with the tax type charged.",
        ["supplier_gstin", "cgst", "sgst", "igst"],
    ),
    "totals_mismatch": (
        "The line amounts, taxes, round-off and stated total do not reconcile within policy tolerance.",
        ["subtotal", "cgst", "sgst", "igst", "round_off", "total"],
    ),
    "vendor_new": (
        "The matched vendor was onboarded fewer than 90 days before the invoice date.",
        ["supplier_name", "invoice_date"],
    ),
    "vendor_unknown": (
        "No vendor-master entry matches the supplier key on this document.",
        ["supplier_gstin", "supplier_name"],
    ),
    "buyer_gstin_mismatch": (
        "The buyer GSTIN printed on the document differs from Meridian's buyer record.",
        ["buyer_gstin"],
    ),
}

REASON_PRIORITY = {
    "bank_details_changed": 0,
    "duplicate": 1,
    "processing_error": 2,
    "suspicious_content": 3,
    "gstin_invalid": 4,
    "vendor_unknown": 5,
    "buyer_gstin_mismatch": 6,
    "tax_type_mismatch": 7,
    "totals_mismatch": 8,
    "vendor_new": 9,
    "foreign_currency": 10,
    "credit_note": 11,
}


def _span(text: str, start: int, end: int) -> dict:
    return {
        "char_start": start,
        "char_end": end,
        "source_text": text[start:end],
    }


def _exact_matches(text: str, value: str, numeric: bool = False) -> list[dict]:
    words = value.strip().split()
    if not words:
        return []
    pattern = r"\s+".join(re.escape(word) for word in words)
    if numeric:
        pattern = rf"(?<![\d.,]){pattern}(?![\d.,])"
    return [_span(text, match.start(), match.end()) for match in re.finditer(pattern, text, re.IGNORECASE)]


def _compact_matches(text: str, value: str, digits_only: bool = False) -> list[dict]:
    def normalize(char: str) -> str:
        if digits_only:
            return char if char.isdigit() else ""
        return char.upper() if char.isalnum() else ""

    normalized_text: list[str] = []
    positions: list[int] = []
    for index, char in enumerate(text):
        normalized = normalize(char)
        if normalized:
            normalized_text.append(normalized)
            positions.append(index)
    needle = "".join(normalize(char) for char in value)
    if not needle:
        return []
    source = "".join(normalized_text)
    matches = []
    cursor = 0
    while True:
        found = source.find(needle, cursor)
        if found < 0:
            break
        start = positions[found]
        end = positions[found + len(needle) - 1] + 1
        matches.append(_span(text, start, end))
        cursor = found + 1
    return matches


def _account_matches(text: str, value: str) -> list[dict]:
    expected = "".join(char for char in value if char.isdigit())
    patterns = (
        re.compile(
            r"(?i)(?:a/c|account|acct)(?:\s*(?:no\.?|number|#))?\s*[:#-]?\s*"
            r"(?P<account>\d[\d -]{4,23}\d)"
        ),
        re.compile(
            r'(?i)"(?:bank[_]?account|account[_]?(?:no|number)|acct[_]?(?:no|number|num)|'
            r'acc[_]?(?:no|num))"\s*:\s*"?'
            r"(?P<account>\d[\d -]{4,23}\d)"
        ),
    )
    matches = {}
    for pattern in patterns:
        for match in pattern.finditer(text):
            account = match.group("account")
            if "".join(char for char in account if char.isdigit()) == expected:
                span = _span(text, match.start("account"), match.end("account"))
                matches[(span["char_start"], span["char_end"])] = span
    return sorted(matches.values(), key=lambda span: span["char_start"])


def _merge_overlapping_matches(text: str, matches: list[dict]) -> list[dict]:
    merged = []
    for match in sorted(matches, key=lambda span: (span["char_start"], span["char_end"])):
        if merged and match["char_start"] < merged[-1]["char_end"]:
            start = merged[-1]["char_start"]
            end = max(merged[-1]["char_end"], match["char_end"])
            merged[-1] = _span(text, start, end)
        else:
            merged.append(match)
    return merged


def _indian_grouping(value: Decimal) -> str:
    fixed = f"{abs(value):.2f}"
    whole, fraction = fixed.split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while head:
            groups.append(head[-2:])
            head = head[:-2]
        whole = ",".join(reversed(groups)) + "," + tail
    sign = "-" if value < 0 else ""
    return f"{sign}{whole}.{fraction}"


def _value_variants(value: object, field: str) -> list[str]:
    if value is None:
        return []
    raw = str(value).strip()
    if not raw:
        return []
    variants = [raw]
    if field == "invoice_date":
        try:
            parsed = date.fromisoformat(raw[:10])
        except ValueError:
            pass
        else:
            variants.extend(
                [
                    parsed.strftime("%d/%m/%Y"),
                    parsed.strftime("%d-%m-%Y"),
                    parsed.strftime("%d.%m.%Y"),
                    parsed.strftime("%m/%d/%Y"),
                ]
            )
    elif field in MONEY_FIELDS or field.endswith((".quantity", ".unit_price", ".amount")):
        try:
            amount = Decimal(raw.replace(",", ""))
        except InvalidOperation:
            pass
        else:
            variants.extend(
                [
                    format(amount.normalize(), "f"),
                    f"{amount:.2f}",
                    f"{amount:,.2f}",
                    _indian_grouping(amount),
                ]
            )
    elif field == "document_type":
        if raw.lower() == "invoice":
            variants.extend(["tax invoice", '"Typ":"INV"'])
        elif raw.lower() == "credit_note":
            variants.extend(["credit note", '"Typ":"CRN"'])
    elif field == "currency" and raw.upper() == "INR":
        variants.extend(["₹", "Rs.", "Rs"])
    return list(dict.fromkeys(variants))


def find_field_evidence(text: str, value: object, field: str) -> dict:
    variants = _value_variants(value, field)
    if not variants:
        return {
            "status": "unavailable",
            "char_start": None,
            "char_end": None,
            "source_text": None,
            "matches": [],
        }

    matches: dict[tuple[int, int], dict] = {}
    numeric = field in MONEY_FIELDS or field.endswith((".quantity", ".unit_price", ".amount"))
    if field == "bank_account":
        found = _account_matches(text, str(value))
    else:
        for variant in variants:
            for match in _exact_matches(text, variant, numeric=numeric):
                matches[(match["char_start"], match["char_end"])] = match
        if not matches and field in COMPACT_FIELDS:
            for match in _compact_matches(text, str(value)):
                matches[(match["char_start"], match["char_end"])] = match
        found = _merge_overlapping_matches(text, list(matches.values()))
    status = "not_found" if not found else "found" if len(found) == 1 else "ambiguous"
    selected = found[0] if len(found) == 1 else None
    return {
        "status": status,
        "char_start": selected["char_start"] if selected else None,
        "char_end": selected["char_end"] if selected else None,
        "source_text": selected["source_text"] if selected else None,
        "matches": found,
    }


def find_suspicious_evidence(text: str) -> list[dict]:
    spans = {}
    for pattern in SUSPICIOUS_PATTERNS:
        for match in pattern.finditer(text):
            spans[(match.start(), match.end())] = _span(text, match.start(), match.end())
    return sorted(spans.values(), key=lambda span: span["char_start"])


def build_invoice_evidence(invoice: dict) -> dict:
    text = invoice.get("raw_text") or ""
    evidence = {}
    for field in (
        "document_type",
        "supplier_name",
        "supplier_gstin",
        "invoice_number",
        "invoice_date",
        "currency",
        *sorted(MONEY_FIELDS),
        "bank_account",
        "ifsc",
        "po_number",
        "notes",
    ):
        evidence[field] = find_field_evidence(text, invoice.get(field), field)
    for index, item in enumerate(invoice.get("line_items") or []):
        for field in ("description", "quantity", "unit_price", "amount"):
            key = f"line_items.{index}.{field}"
            evidence[key] = find_field_evidence(text, item.get(field), key)

    buyer_gstin = _extract_buyer_gstin_from_text(text)
    if buyer_gstin:
        evidence["buyer_gstin"] = find_field_evidence(text, buyer_gstin, "supplier_gstin")
    return evidence


def build_review_details(
    invoice: dict,
    evidence: dict,
    duplicate_matches: list[dict] | None = None,
) -> list[dict]:
    details = []
    for code in invoice.get("review_reasons") or []:
        description, supporting_fields = REVIEW_REASON_DETAILS.get(
            code,
            ("This document needs review under Meridian's AP policy.", []),
        )
        line_fields = (
            [key for key in evidence if key.startswith("line_items.") and key.endswith(".amount")]
            if code == "totals_mismatch"
            else []
        )
        direct_matches = find_suspicious_evidence(invoice.get("raw_text") or "") if code == "suspicious_content" else []
        details.append(
            {
                "code": code,
                "title": code.replace("_", " ").capitalize(),
                "description": description,
                "evidence_fields": [*supporting_fields, *line_fields],
                "direct_evidence": direct_matches,
                "reference_matches": duplicate_matches if code == "duplicate" else [],
            }
        )
    return details


def review_priority(status: str, reasons: list[str]) -> tuple[int, str]:
    if status != "needs_review":
        return 99, "Routine"
    rank = min((REASON_PRIORITY.get(reason, 50) for reason in reasons), default=50)
    if rank <= 3:
        return rank, "Critical"
    if rank <= 8:
        return rank, "High"
    return rank, "Standard"


def _extract_buyer_gstin_from_text(text: str) -> str | None:
    match = re.search(
        r"^\s*(?:buyer(?:\s*\(bill\s*to\))?|\bbill\s*to)\b.{0,200}?"
        r"(?:GSTIN(?:/UIN)?|GSTIN)\s*[:#]?\s*([0-9A-Z]{15})",
        text,
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    return match.group(1).upper() if match else None
