# Decisions

## Architecture

The LLM extracts invoice fields; Python validates them against reference data and applies routing and approval rules. Invoice text is treated as untrusted input. Known vendor account numbers and labeled account-number fields are redacted before external extraction; reference files and policy text are not in the prompt. Processing failures remain review items.

The API links extracted values and reasons to exact source spans, marking absent or repeated matches instead of guessing. The reviewer UI prioritizes risk and renders source text safely. Approval and rejection are audited server-side actions; retries do not create duplicate approvals or payments.

## Part 4: what I went deep on, and why

**Option A — Evidence-Linked Review.** I chose A because reviewers said they re-key values when they cannot see the source, and payment mistakes have material exposure: Farhan cited a ₹3.8 lakh bank-change fraud, while AP estimates each manual touch at ₹85. Source-linked fields, reason evidence and idempotent decisions address those trust and control gaps. Option B's cost/quality optimization is valuable, but there was no authorized live-provider baseline to measure it against. Option C offered no clearer near-term benefit. A does not relax the written human-approval rule.

## Replies to stakeholders

### Anita Rao, CFO

The requested under-₹10,000 no-touch path could affect about 1,200 monthly documents; at ₹85 per touch, that is up to ₹1.02 lakh in possible monthly review savings if each currently needs a touch. I have not enabled it: policy requires human approval for every invoice, and amount alone is not authorization. I also will not let the model silently repair a garbled GSTIN. It must match the printed value and reference data or be reviewed. I propose a formal policy amendment and tested controls before considering either exception.

### Farhan Sheikh, Head of AP

The reviewer now links extracted values and reason cards to exact source text; missing or repeated matches are disclosed rather than guessed. Approval retries are idempotent, with one payment instruction per invoice. Bank changes are detected and sent to review, but the written policy does not require a callback, and the vendor master has no trusted phone number. I have not implemented a callback block or claimed the issue is solved: the cited ₹3.8 lakh loss makes it urgent, but Finance must first approve the workflow and data source. No real-provider comparison is available to justify a “most accurate” model choice.

### Deepak Menon, CTO

I corrected listed model prices and removed the redundant verification call; unknown model costs now show as unpriced, not free. At ₹88/USD, the reported $165 over 2,400 documents implies about ₹6.05 per document, not a ₹15 monthly total, but token estimates cannot reconcile an account invoice. I made no live calls, so the ₹1.50 and 10-second p95 targets remain unverified. I will not recommend fine-tuning without a representative quality, cost and latency benchmark and a data-governance review.

### Priya Natarajan, Data Protection Officer

The extraction prompt receives invoice text after known vendor account numbers and labeled account-number fields are redacted; vendor/reference files and policy text are not sent. Other invoice content, including names, GSTINs, IFSCs, amounts and notes, may still go to the configured provider. Unlabeled or obfuscated account numbers may evade the current masking, so I cannot promise complete redaction for every layout. I will not claim production readiness until you review representative redaction tests and provider access, retention and processing terms.

### Sunil Joshi, Finance Controller

I have not routed every invoice to review or enabled automatic approval. The October hand-checked 13% issue rate suggests roughly 390 reviews out of 3,000, or about ₹33,150 in clerk time at ₹85 each; that is an estimate, not a measured Ledgerline production rate. The dev set is deliberately enriched, and the fake model caused 10 unnecessary reviews among 11 labeled-clean cases by repeating one invoice, so that is not a forecast. The queue prioritizes risk. Callback blocking and any approval exception need your formal policy decision; I will not silently change AP_POLICY.

### Ravi Kulkarni, contractor

I agree the model is useful for extracting varied layouts, but it should not decide whether money can be paid: the starter lets its `requires_review` output control routing. Its “94%” is not reproduced; the fake run scored 75/288 fields (26%) and the eval prompt included labeled dev examples. The fake is not live-model evidence. I will not put payment rules back in the prompt. I agree code releases slow Finance down, so I propose a versioned, validated policy configuration with Finance sign-off, tests and an audit trail. Until approved and built, changes still require controlled code review and release.

## Policy changes I propose

- Define a bank-change callback workflow: trusted phone source, verifier, audit record and payment hold/release criteria. Until approved and implemented, the existing written review rule remains in force.
- Decide which critical fields require review when source evidence is missing or ambiguous; never treat an unlocated value as verified.
- Consider a versioned policy-configuration process with Finance approval, validation, tests and audit history. Do not silently change `AP_POLICY.md` or let prompt text override it.
- Keep human approval mandatory unless the Finance Controller formally amends the policy and approves tested controls for an exception.
