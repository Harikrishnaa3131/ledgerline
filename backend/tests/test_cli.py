import json
from argparse import Namespace

from ledgerline.cli import predict


def test_unreadable_document_gets_processing_error_output(tmp_path, monkeypatch, ref):
    source = tmp_path / "input"
    source.mkdir()
    (source / "bad.txt").write_bytes(b"\xff")
    output = tmp_path / "predictions.jsonl"
    monkeypatch.setattr("ledgerline.cli.load_reference", lambda _: ref)
    predict(
        Namespace(
            input=str(source),
            output=str(output),
            reference=None,
            db=str(tmp_path / "ledger.db"),
        )
    )
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["needs_review"] is True
    assert rows[0]["review_reasons"] == ["processing_error"]
    assert rows[0]["evidence"]["invoice_number"]["status"] == "unavailable"
