from ledgerline.evidence import build_invoice_evidence, find_field_evidence


def test_amount_match_preserves_exact_source_span():
    text = "Total Rs. 23,458.00"
    evidence = find_field_evidence(text, 23458.0, "total")
    assert evidence["status"] == "found"
    assert text[evidence["char_start"] : evidence["char_end"]] == "23,458.00"
    assert evidence["source_text"] == "23,458.00"


def test_repeated_values_report_ambiguity_without_picking_a_span():
    text = "Subtotal 23,458.00; total 23,458.00"
    evidence = find_field_evidence(text, "23458.00", "total")
    assert evidence["status"] == "ambiguous"
    assert evidence["char_start"] is None
    assert evidence["source_text"] is None
    assert all(text[m["char_start"] : m["char_end"]] == m["source_text"] for m in evidence["matches"])


def test_dates_match_common_printed_format_and_missing_values_are_uncertain():
    text = "Dated: 25/04/2026"
    evidence = find_field_evidence(text, "2026-04-25", "invoice_date")
    assert evidence["source_text"] == "25/04/2026"
    missing = find_field_evidence(text, "SIS/26-27/0042", "invoice_number")
    assert missing["status"] == "not_found"
    assert missing["char_start"] is None


def test_alternative_variants_for_one_occurrence_are_not_reported_as_ambiguous():
    text = "TAX INVOICE"
    evidence = find_field_evidence(text, "invoice", "document_type")
    assert evidence["status"] == "found"
    assert evidence["source_text"] == text


def test_bank_account_evidence_requires_a_labeled_exact_account():
    text = "Account No: 12 345 678\nReference: 12345678"
    evidence = find_field_evidence(text, "12345678", "bank_account")
    assert evidence["status"] == "found"
    assert evidence["source_text"] == "12 345 678"

    unlabeled = find_field_evidence("Reference: 12345678", "12345678", "bank_account")
    assert unlabeled["status"] == "not_found"


def test_offsets_use_python_character_indices():
    text = "🧾 Invoice: SIS/26-27/0042"
    evidence = find_field_evidence(text, "SIS/26-27/0042", "invoice_number")
    assert evidence["char_start"] == 11
    assert text[evidence["char_start"] : evidence["char_end"]] == "SIS/26-27/0042"


def test_line_item_evidence_is_addressable_by_field_key():
    text = "4 x Widget @ ₹10.00 = ₹40.00"
    invoice = {
        "raw_text": text,
        "line_items": [{"description": "Widget", "quantity": 4, "unit_price": 10.0, "amount": 40.0}],
    }
    evidence = build_invoice_evidence(invoice)
    assert evidence["line_items.0.description"]["source_text"] == "Widget"
    assert evidence["line_items.0.quantity"]["source_text"] == "4"
    assert evidence["line_items.0.unit_price"]["source_text"] == "10.00"
    assert evidence["line_items.0.amount"]["source_text"] == "40.00"
