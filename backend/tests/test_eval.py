from pathlib import Path
from types import SimpleNamespace

from eval import run_eval
from ledgerline import db


def test_eval_counts_exception_as_failure_and_keeps_fixed_denominator(tmp_path, monkeypatch, capsys, ref):
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(
        run_eval,
        "get_settings",
        lambda: SimpleNamespace(data_dir=repo_root / "data"),
    )
    monkeypatch.setattr(run_eval, "load_reference", lambda: ref)
    connect = db.connect
    monkeypatch.setattr(run_eval.db, "connect", lambda _: connect(str(tmp_path / "eval.db")))
    calls = 0

    def process_document(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("recorded provider failure")
        return {
            "document_type": "",
            "supplier_name": "",
            "supplier_gstin": "",
            "invoice_number": "",
            "invoice_date": "",
            "currency": "",
            "subtotal": "",
            "cgst": "",
            "sgst": "",
            "igst": "",
            "total": "",
            "po_number": "",
            "needs_review": False,
        }

    monkeypatch.setattr(run_eval, "process_document", process_document)
    run_eval.main()
    output = capsys.readouterr().out
    assert "Processing failures: 1/24" in output
    assert "Field accuracy: " in output and "/288" in output
