# Findings

## Evidence boundary

No Anthropic or OpenAI key is configured in the local `.env`, so I did not make live provider calls. The AP policy also forbids sending vendor bank numbers externally; the starter prompt includes those numbers in invoice text, the vendor CSV and leaked examples. I instead ran the untouched starter with `LLM_PROVIDER=fake`, from `backend/`, over all 24 dev documents and ran its eval. This is an offline diagnostic, **not** provider-quality or billing evidence.

The fake starter wrote 24/24 rows but returned the same Sitara invoice for every document. Its eval was 75/288 fields (26.0%); `dev_001` happened to match the evaluated fields, and each of `dev_002`–`dev_024` had at least one mismatch. It routed ready for all 13 labeled-review documents: `dev_004`, `dev_005`, `dev_007`, `dev_008`, `dev_010`, `dev_011`, `dev_012`, `dev_013`, `dev_014`, `dev_015`, `dev_018`, `dev_019`, and `dev_024`. The prompt also embedded the labeled `dev_001`–`dev_003` examples in every eval request. I cannot claim which documents a real model would fail or reconcile the CTO's bill without an authorized, privacy-safe live run.

## Top eight, highest business risk first

### F1: Bank changes are not cross-checked against the vendor master

- **Severity / rank:** Critical; a changed account can divert a full invoice payment.
- **Evidence:** In the starter fake run, `dev_005` was emitted as ready with no reasons and the unrelated Sitara number `SIS/26-27/0042`, total ₹23,458. The document is Vardhan invoice `VL/0931` for ₹1,41,600 and shows a changed account. The fake output is not evidence of real-model extraction, but it does show the starter's untrusted model decision was not made safe by validation.
- **Exposure estimate:** Up to ₹1,41,600 for this invoice, not an expected-loss estimate.
- **Fix / regression:** Extract bank account and IFSC locally; redact them from prompts; match domestic vendors by GSTIN and compare both details. `test_bank_details_are_extracted_locally_and_mismatch_is_reviewed`, `test_prompt_excludes_reference_policy_examples_and_bank_accounts`, and validation tests. **Fixed in worktree.**

### F2: Duplicate invoice identity is not normalized

- **Severity / rank:** Critical; a second document can trigger a second payout.
- **Evidence:** Starter fake run `dev_015` was ready with `SIS/26-27/0042` and ₹23,458. The labeled document is invoice `SIS/26-27/0018`, ₹34,220, already paid. Existing duplicate checks compared supplier display name and printed invoice number literally, not supplier key, normalized number and FY.
- **Exposure estimate:** Up to ₹34,220 for this duplicate.
- **Fix / regression:** Normalize punctuation/case while preserving leading zeros; key domestic vendors by GSTIN, include FY, ignore credit notes, and serialize check-plus-insert for batches. `test_same_batch_duplicate_uses_supplier_and_fiscal_year` and duplicate tests. **Fixed in worktree.**

### F3: Prompt text controls review routing

- **Severity / rank:** Critical; hostile invoice text can request a ready decision.
- **Evidence:** The fake starter emitted `dev_012` ready with no reasons and ₹23,458; the labeled document is a prompt-injection attempt on a ₹66,434 invoice. A fake cannot demonstrate whether a live model would obey it, but in the starter the model's `requires_review` field directly controlled routing.
- **Exposure estimate:** Up to ₹66,434 for this invoice.
- **Fix / regression:** Remove policy decisions and review fields from model output; route only on deterministic checks and flag suspicious AI-directed text/markup. `test_routing_ignores_model_decision_and_flags_prompt_injection`. **Fixed in worktree.**

### F4: Approval retries can create multiple payment instructions

- **Severity / rank:** Critical; AP reported Treasury caught a duplicate entry, and the endpoint inserted a payment on every qualifying retry.
- **Evidence:** Starter `approve_invoice` incremented raw approval count and inserted payments without a transaction, distinct-person check or idempotency guard.
- **Exposure estimate:** A repeated request can duplicate the full invoice amount; no live incident amount was supplied.
- **Fix / regression:** SQLite write transaction, unique approver/payment indexes, distinct-user count, duplicate/credit-note guard and review-note enforcement. API retry and two-approver tests. **Fixed in worktree.**

### F5: Supplier and buyer GSTIN checks are incomplete

- **Severity / rank:** High; identity and tax-state mistakes can misdirect payments or cause tax exposure.
- **Evidence:** Starter GSTIN validation checked format only, vendor matching used printed name, and buyer state was hard-coded. Thus a bad check digit or altered name could evade or misdirect checks.
- **Exposure estimate:** Not responsibly quantifiable from the dev set.
- **Fix / regression:** Validate GSTIN checksum; match domestic vendors by GSTIN; derive state from `buyer.json`. Buyer-GSTIN mismatch detection is an off-by-default `LEDGERLINE_FLAG_BUYER_GSTIN_MISMATCH=1` extension because the policy has no such review code. **Fixed, with that flagged policy extension.**

### F6: Arithmetic checks use floats and omit round-off

- **Severity / rank:** High; a bad total may be approved or a valid invoice may be over-reviewed.
- **Evidence:** Starter compared floats with exact equality and omitted round-off from the total calculation; it did not reconcile line sums/subtotals.
- **Fix / regression:** Decimal parsing and deterministic line, subtotal, tax-type and total reconciliation using the policy's ₹1 tolerance. Tax *rates* cannot be independently checked because the supplied policy/reference data provide no rate schedule. Tests cover exact tolerance and mismatches. **Fixed within available policy data.**

### F7: Cost estimates silently understate known model rates

- **Severity / rank:** Medium-high; the reported budget is not trustworthy.
- **Evidence:** The starter's Opus 5.5 input rate was `$0.004/MTok`; Anthropic's published rate is `$4/MTok` (a 1,000x difference). Similar scale errors appear in the listed Sonnet/Haiku and GPT-4o-mini entries. Two LLM passes also doubled call volume. Source: [Anthropic model pricing](https://platform.claude.com/docs/en/about-claude/pricing).
- **Fix / regression:** Correct listed rates, remove the redundant verification call, and report unknown-model cost as unpriced rather than zero. Pricing tests. **Fixed for listed models; provider invoice reconciliation remains unverified.**

### F8: Eval leakage and exceptions make the headline score unsafe

- **Severity / rank:** Medium; it can mask the high-risk failures above.
- **Evidence:** `dev_001`–`dev_003` were included as few-shot labeled examples in every request, including their own eval rows. The starter eval skipped exceptions, and CLI omitted failed documents.
- **Fix / regression:** Remove dev examples from prompts; count exceptions as failures with a fixed denominator; emit `processing_error` rows rather than skip unreadable documents. Eval and CLI tests. **Fixed in worktree.**

## Additional issues and limits

- The offline post-fix fake run still has 26.0% field accuracy because the fake returns one canned invoice; this is not a quality comparison.
- Provider cost is calculated from returned token counts and public list rates, converted at the existing planning rate of ₹88/USD. Account-specific discounts, cached-token billing and the October invoice cannot be reconciled without a real authorized run and bill.
- No tax-rate table exists, so the code checks state tax type and arithmetic reconciliation, not whether a statutory percentage is correct.
- Farhan's callback-before-bank-change workflow is not implemented: the vendor master has no phone number, and policy requires review rather than a callback block.
- The new buyer-GSTIN reason is disabled unless its flag is set; Finance must approve adding that reason to policy before enabling it in production.
- **Not sure this is a problem:** duplicate detection scans stored invoices rather than using a normalized-key index. At about 3,000 documents/month it may be adequate; measure the production p95 before adding schema complexity.
