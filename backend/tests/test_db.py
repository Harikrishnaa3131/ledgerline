import sqlite3

import pytest

from ledgerline.db import _migrate_invoice_money, _migrate_payment_money, connect, to_paise


def test_persisted_invoice_and_line_item_money_is_exact(tmp_path):
    conn = connect(str(tmp_path / "ledger.db"))
    assert to_paise("23458.00") == 2345800
    with pytest.raises(ValueError, match="more than two decimal places"):
        to_paise("1.001")
    conn.close()


def test_legacy_invoice_money_migrates_to_integer_paise(tmp_path):
    conn = sqlite3.connect(tmp_path / "legacy-invoice.db")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE invoices (id INTEGER PRIMARY KEY, subtotal REAL, cgst REAL, sgst REAL, "
        "igst REAL, round_off REAL, total REAL)"
    )
    conn.execute("INSERT INTO invoices VALUES (1, 100.00, 9.00, 9.00, 0.00, -0.40, 117.60)")
    _migrate_invoice_money(conn)
    row = conn.execute(
        "SELECT total, total_paise, typeof(total_paise) FROM invoices WHERE id = 1"
    ).fetchone()
    assert (row["total"], row["total_paise"], row["typeof(total_paise)"]) == (None, 11760, "integer")
    conn.close()


def test_legacy_payment_money_migrates_to_integer_paise(tmp_path):
    conn = sqlite3.connect(tmp_path / "legacy-payment.db")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY)")
    conn.execute(
        "CREATE TABLE payments (id INTEGER PRIMARY KEY, invoice_id INTEGER, amount REAL, created_at TEXT)"
    )
    conn.execute("INSERT INTO invoices VALUES (1)")
    conn.execute("INSERT INTO payments VALUES (1, 1, 23458.00, '2026-01-01')")
    _migrate_payment_money(conn)
    row = conn.execute(
        "SELECT amount_paise, typeof(amount_paise) FROM payments WHERE id = 1"
    ).fetchone()
    assert (row["amount_paise"], row["typeof(amount_paise)"]) == (2345800, "integer")
    conn.close()
