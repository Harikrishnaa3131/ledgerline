"""Field accuracy on the labelled dev set.  Usage (from backend/):  python eval/run_eval.py"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledgerline import db
from ledgerline.config import get_settings
from ledgerline.pipeline import process_document
from ledgerline.reference import load_reference

FIELDS = ["document_type", "supplier_name", "supplier_gstin", "invoice_number", "invoice_date", "currency",
          "subtotal", "cgst", "sgst", "igst", "total", "po_number"]


def _norm(value) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value).strip().lower()


def main() -> None:
    settings = get_settings()
    ref = load_reference()
    conn = db.connect(str(Path(tempfile.mkdtemp()) / "eval.db"))
    with open(settings.data_dir / "ground_truth" / "dev.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]

    correct = total = failures = review_misses = 0
    for row in rows:
        path = settings.data_dir / "invoices" / "dev" / row["filename"]
        try:
            got = process_document(conn, ref, path.read_text(encoding="utf-8"), row["document_id"])
        except Exception as exc:  # noqa: BLE001 - any document exception is an evaluation failure
            print(f"processing_error {row['document_id']}: {type(exc).__name__}")
            got = {}
            failures += 1
        if "processing_error" in (got.get("review_reasons") or []):
            failures += 1
        expected_review = bool(row["expected"].get("needs_review"))
        actual_review = bool(got.get("needs_review"))
        if expected_review and not actual_review:
            review_misses += 1
        for field in FIELDS:
            total += 1
            correct += _norm(got.get(field)) == _norm(row["expected"].get(field))
    print(f"Field accuracy: {correct}/{total} = {correct / total:.1%}")
    print(f"Processing failures: {failures}/{len(rows)}")
    print(f"Missed reviews: {review_misses}")


if __name__ == "__main__":
    main()
