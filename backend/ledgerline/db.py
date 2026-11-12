"""SQLite persistence."""
from __future__ import annotations

import json
import sqlite3
from decimal import ROUND_HALF_UP, Decimal

from .config import USD_TO_INR

MONEY_FIELDS = ("subtotal", "cgst", "sgst", "igst", "round_off", "total")

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    filename TEXT,
    raw_text TEXT NOT NULL,
    document_type TEXT,
    supplier_name TEXT,
    supplier_gstin TEXT,
    invoice_number TEXT,
    invoice_date TEXT,
    currency TEXT,
    subtotal REAL,
    cgst REAL,
    sgst REAL,
    igst REAL,
    round_off REAL,
    total REAL,
    subtotal_paise INTEGER,
    cgst_paise INTEGER,
    sgst_paise INTEGER,
    igst_paise INTEGER,
    round_off_paise INTEGER,
    total_paise INTEGER,
    bank_account TEXT,
    ifsc TEXT,
    po_number TEXT,
    notes TEXT,
    line_items_json TEXT,
    warnings_json TEXT,
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_reasons_json TEXT,
    required_approvals INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'ready_for_approval',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    user_id TEXT NOT NULL,
    note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    user_id TEXT NOT NULL,
    note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(invoice_id)
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    amount_paise INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER REFERENCES invoices(id),
    document_id TEXT,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    latency_ms INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate_invoice_money(conn)
    _migrate_payment_money(conn)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_approvals_invoice_user ON approvals(invoice_id, user_id)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_one_per_invoice ON payments(invoice_id)")
    conn.commit()
    return conn


def to_paise(amount: Decimal | float | str | None) -> int | None:
    if amount is None:
        return None
    paise = Decimal(str(amount)) * 100
    if paise != paise.to_integral_value():
        raise ValueError("Money amount has more than two decimal places")
    return int(paise)


def _legacy_to_paise(amount: float | None) -> int | None:
    if amount is None:
        return None
    rounded = (Decimal(str(amount)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(rounded)


def from_paise(paise: int | None) -> float | None:
    return float(Decimal(paise) / 100) if paise is not None else None


def get_total_paise(conn: sqlite3.Connection, invoice_id: int) -> int | None:
    row = conn.execute("SELECT total_paise FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    return row["total_paise"] if row else None


def _migrate_invoice_money(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(invoices)")}
    for field in MONEY_FIELDS:
        paise_field = f"{field}_paise"
        if paise_field not in columns:
            conn.execute(f"ALTER TABLE invoices ADD COLUMN {paise_field} INTEGER")
    legacy_fields = ", ".join(MONEY_FIELDS)
    paise_fields = ", ".join(f"{field}_paise" for field in MONEY_FIELDS)
    rows = conn.execute(
        f"SELECT id, {legacy_fields}, {paise_fields} FROM invoices"
    ).fetchall()
    assignments = ", ".join(f"{field}_paise = ?" for field in MONEY_FIELDS)
    for row in rows:
        values = [
            row[f"{field}_paise"]
            if row[f"{field}_paise"] is not None
            else _legacy_to_paise(row[field])
            for field in MONEY_FIELDS
        ]
        if any(value is not None for value in values):
            conn.execute(f"UPDATE invoices SET {assignments} WHERE id = ?", (*values, row["id"]))
    conn.execute(f"UPDATE invoices SET {', '.join(f'{field} = NULL' for field in MONEY_FIELDS)}")


def _migrate_payment_money(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(payments)")}
    if "amount_paise" in columns:
        return
    rows = conn.execute("SELECT id, invoice_id, amount, created_at FROM payments").fetchall()
    conn.execute("DROP INDEX IF EXISTS idx_payments_one_per_invoice")
    conn.execute("ALTER TABLE payments RENAME TO payments_legacy")
    conn.execute(
        "CREATE TABLE payments (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "invoice_id INTEGER NOT NULL REFERENCES invoices(id), amount_paise INTEGER NOT NULL, "
        "created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    for row in rows:
        conn.execute(
            "INSERT INTO payments (id, invoice_id, amount_paise, created_at) VALUES (?, ?, ?, ?)",
            (row["id"], row["invoice_id"], _legacy_to_paise(row["amount"]), row["created_at"]),
        )
    conn.execute("DROP TABLE payments_legacy")


def get_invoice(conn: sqlite3.Connection, invoice_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if row is None:
        return None
    inv = dict(row)
    for col in ("line_items_json", "warnings_json", "review_reasons_json"):
        inv[col.removesuffix("_json")] = json.loads(inv.pop(col) or "[]")
    for field in MONEY_FIELDS:
        inv[field] = from_paise(inv.pop(f"{field}_paise"))
    for item in inv["line_items"]:
        for field in ("quantity", "unit_price", "amount"):
            if item[field] is not None:
                item[field] = float(item[field])
    inv["needs_review"] = bool(inv["needs_review"])
    usage = conn.execute(
        "SELECT COUNT(*) AS calls, COALESCE(SUM(input_tokens), 0) AS input_tokens, "
        "COALESCE(SUM(output_tokens), 0) AS output_tokens, COALESCE(SUM(cost_usd), 0) AS cost_usd, "
        "COUNT(cost_usd) AS priced_calls, "
        "COALESCE(SUM(latency_ms), 0) AS latency_ms FROM llm_calls WHERE invoice_id = ?",
        (invoice_id,),
    ).fetchone()
    unpriced_calls = usage["calls"] - usage["priced_calls"]
    inv["usage"] = {
        "llm_calls": usage["calls"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cost_inr": round(usage["cost_usd"] * USD_TO_INR, 4) if not unpriced_calls else None,
        "unpriced_calls": unpriced_calls,
        "latency_ms": usage["latency_ms"],
    }
    return inv
