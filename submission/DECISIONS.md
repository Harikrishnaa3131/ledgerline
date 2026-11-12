# Decisions

## Architecture

The LLM extracts invoice fields; Python validates policy and controls routing. The extraction prompt treats invoice text as untrusted data and redacts bank account numbers before an external call. Deterministic validation uses reference data and decimal arithmetic. Failures are retained as review items rather than silently discarded.

The API attaches source spans only when it can locate an exact value; repeated or missing matches are explicitly marked ambiguous or not found. The reviewer UI renders original text as text, links extracted values and reason evidence to highlights, and prioritizes higher-risk reviews. Approval and rejection are server-side, transaction-backed, audited actions; repeated approvals do not create duplicate payments.

## Part 4: what I went deep on, and why

**Option A — Evidence-Linked Review.** I chose this because AP reviewers said they re-key values when they cannot see their source, while the production risk includes fraudulent bank changes and accidental duplicate payments. Field-level evidence, plain-language reasons, a prioritized queue, and retry-safe decisions address those problems more directly than optimizing model cost alone. The interface does not bypass the policy's human approval requirement.

## Replies to stakeholders

### Anita Rao, CFO

I would not enable straight-through approval: the current policy requires a human approval for every invoice. OCR should not silently “correct” a GSTIN; it must match the printed value and vendor reference or be reviewed.

### Farhan Sheikh, Head of AP

The reviewer can inspect extracted values against source spans and reason evidence. Bank changes are flagged, but the callback control is not implemented because the vendor master has no phone number or verification workflow.

### Deepak Menon, CTO

The dashboard reports token-based estimates at configured rates, not a provider invoice reconciliation. No real-provider cost or latency benchmark was available for this work, so neither the ₹1.50 target nor p95 target is claimed as met. Fine-tuning is outside this change.

### Priya Natarajan, Data Protection Officer

Known and labeled bank account numbers are redacted before the document is sent to the extraction provider. Other invoice content still leaves Meridian when an external provider is configured; provider access and retention need review before rollout.

### Sunil Joshi, Finance Controller

The queue prioritizes risk rather than routing every document to review, while preserving the written approval rule. The disputed call-back workflow needs an agreed phone-data source and an auditable verification step before implementation.

### Ravi Kulkarni, contractor

The model remains useful for varied layouts and names, but it does not decide whether an invoice is payable. Policy rules are deterministic and tested; policy changes therefore need controlled code review and release.

## Policy changes I propose

- Define an auditable vendor callback process for bank-detail changes, including the trusted phone source and who records verification. Until then, keep these invoices blocked from payment.
- Specify when a critical extracted field with missing or ambiguous source evidence must be reviewed. Do not treat an unlocated value as verified.
- Keep human approval mandatory unless the Finance Controller formally changes the policy and approves tested controls for any exception.
