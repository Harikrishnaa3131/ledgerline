from ledgerline.extraction import build_extraction_prompt


def test_prompt_excludes_reference_policy_examples_and_bank_accounts(ref):
    prompt = build_extraction_prompt("A/c No: 7781002233445\nGSTIN 27AAJFV6651D1ZZ", ref)
    assert "7781002233445" not in prompt
    assert "VENDOR MASTER" not in prompt
    assert "AP POLICY" not in prompt
    assert "dev_001" not in prompt
    assert "[REDACTED_ACCOUNT]" in prompt
