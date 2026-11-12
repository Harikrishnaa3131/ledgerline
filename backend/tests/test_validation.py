from datetime import date

from ledgerline.models import Invoice, LineItem
from ledgerline.validation import (
    check_bank_details,
    check_duplicate,
    check_suspicious_content,
    check_tax_type,
    check_totals,
    check_vendor_new,
    find_vendor,
    is_valid_gstin,
    normalize_invoice_number,
)

SITARA_GSTIN = "27AAKCS4821M1ZW"
NARMADA_GSTIN = "24AAOFN2207Q1ZX"


def make_invoice(**overrides) -> Invoice:
    fields = dict(
        document_type="invoice",
        supplier_name="Sitara Industrial Supplies Pvt. Ltd.",
        supplier_gstin=SITARA_GSTIN,
        invoice_number="SIS/26-27/0042",
        invoice_date=date(2026, 4, 25),
        currency="INR",
        subtotal=100.0,
        cgst=9.0,
        sgst=9.0,
        igst=0.0,
        round_off=0.0,
        total=118.0,
        bank_account=None,
        ifsc=None,
        po_number=None,
        notes=None,
        line_items=[LineItem("Widget", 1.0, 100.0, 100.0)],
    )
    fields.update(overrides)
    return Invoice(**fields)


def test_valid_gstin_accepted():
    assert is_valid_gstin(SITARA_GSTIN)


def test_short_gstin_rejected():
    assert not is_valid_gstin("27AAKCS4821M")


def test_missing_gstin_rejected():
    assert not is_valid_gstin(None)


def test_gstin_checksum_is_verified():
    assert not is_valid_gstin(SITARA_GSTIN[:-1] + "A")


def test_domestic_vendor_is_matched_by_gstin_not_printed_name(ref):
    vendor = find_vendor(ref, SITARA_GSTIN, "Untrusted printed name", "INR")
    assert vendor["vendor_id"] == "V0030"


def test_foreign_vendor_name_ignores_punctuation_and_spacing(ref):
    vendor = find_vendor(ref, None, "Cloud Nimbus, Inc.", "USD")
    assert vendor["vendor_id"] == "V0004"


def test_vendor_onboarded_within_90_days_needs_review(ref):
    invoice = make_invoice(
        supplier_name="Shakti Castings Pvt. Ltd.",
        supplier_gstin="27AAPCS5512H1Z4",
        invoice_date=date(2026, 4, 12),
    )
    vendor = find_vendor(ref, invoice.supplier_gstin, invoice.supplier_name, "INR")
    assert check_vendor_new(invoice, vendor) == ["vendor_new"]


def test_normalized_invoice_number_removes_punctuation_and_case():
    assert normalize_invoice_number("SIS / 26-27 #0018.") == "SIS26270018"


def test_inter_state_igst_is_fine():
    invoice = make_invoice(supplier_gstin=NARMADA_GSTIN, cgst=0.0, sgst=0.0, igst=18.0)
    assert check_tax_type(invoice) == []


def test_totals_match():
    assert check_totals(make_invoice()) == []


def test_totals_mismatch_detected():
    assert check_totals(make_invoice(total=150.0)) == ["totals_mismatch"]


def test_totals_tolerance_includes_exactly_one_rupee():
    assert check_totals(make_invoice(total=119.0)) == []
    assert check_totals(make_invoice(total=119.01)) == ["totals_mismatch"]


def test_duplicate_of_paid_invoice(conn, ref):
    invoice = make_invoice(invoice_number="SIS 26.27 #0018")
    assert check_duplicate(conn, ref, invoice) == ["duplicate"]


def test_new_invoice_is_not_a_duplicate(conn, ref):
    assert check_duplicate(conn, ref, make_invoice()) == []


def test_credit_note_is_not_checked_for_duplicate(conn, ref):
    invoice = make_invoice(document_type="credit_note", invoice_number="SIS/26-27/0018")
    assert check_duplicate(conn, ref, invoice) == []


def test_same_batch_duplicate_uses_supplier_and_fiscal_year(conn, ref):
    first = make_invoice(invoice_number="SIS / 26-27 / 0042")
    conn.execute(
        "INSERT INTO invoices (org_id, document_id, raw_text, document_type, supplier_name, supplier_gstin, "
        "invoice_number, invoice_date, currency) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "meridian", "first_doc", "", "invoice", first.supplier_name, first.supplier_gstin,
            first.invoice_number, "2026-04-25", "INR",
        ),
    )
    assert check_duplicate(conn, ref, make_invoice(invoice_number="sis-26.27.0042")) == ["duplicate"]
    other_fy = make_invoice(invoice_number="SIS/26-27/0042", invoice_date=date(2025, 3, 31))
    assert check_duplicate(conn, ref, other_fy) == []


def test_bank_account_and_ifsc_are_normalized():
    vendor = {"bank_account": "00123456", "ifsc": "BANK0001234"}
    assert check_bank_details(make_invoice(bank_account="00 123-456", ifsc="bank0001234"), vendor) == []
    assert check_bank_details(make_invoice(ifsc="BANK0009999"), vendor) == ["bank_details_changed"]


def test_email_address_angle_brackets_are_not_html():
    assert check_suspicious_content('From: "Accounts" <accounts@vendor.example>') == []
    assert check_suspicious_content("<script>alert(1)</script>") == ["suspicious_content"]
