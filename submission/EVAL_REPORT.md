# Evaluation report

## Setup

Run on 12 November 2026 against all 24 dev documents and their labels. I used the same `LLM_PROVIDER=fake` implementation for the historical starter (`0fc124c`) and current pipeline. No Anthropic or OpenAI key is configured, so I made **no real provider calls**. The fake is deterministic: it returns the same Sitara extraction for every document and reports a fixed 5 ms per call. These results are a pipeline regression check, not a model-quality, latency, or billing measurement.

From `backend\`:

```powershell
$env:LLM_PROVIDER = "fake"
.\.venv\Scripts\python.exe -m ledgerline.cli predict --input ..\data\invoices\dev --reference ..\data\reference --output ..\submission\predictions_dev.jsonl
.\.venv\Scripts\python.exe eval\run_eval.py
```

I ran the starter from its original commit in a temporary archive, then ran the same command against the current worktree. Both wrote 24/24 records; the current eval reported 0 processing failures and 0 missed review labels.

## What the “94%” actually measured

The handover says 94.2%, but the starter's `eval/run_eval.py` measures only 12 fields per document (288 comparisons on 24 documents): type, supplier/name/GSTIN, invoice number/date, currency, subtotal, CGST, SGST, IGST, total and PO. It does not score review reasons or routing, bank account/IFSC, round-off, line items, approvals, latency or cost. It normalizes amounts through `float`, and catches exceptions by printing “skipping” and removing those documents from the denominator.

The starter prompt also embeds labeled `dev_001`–`dev_003` examples in every extraction request, including their own eval requests. With the available fake provider, the original starter scores **75/288 = 26.0%**, not 94.2%. I reran the starter with only those examples removed from the prompt; it remains **75/288 = 26.0%** because the fake returns the same canned output regardless of prompt. The corrected fixed-denominator score also remains 75/288: this run had no errors to add as failures. This cannot tell us how much leakage inflated a real-model result, nor reproduce the handover's real-model claim.

## What I chose to measure, and why

Field accuracy gives continuity with the handover, but routing errors are the business-critical measure. I therefore compared review misses and unnecessary reviews against `needs_review` labels, counted processing failures against all 24 inputs, and recorded calls, provider-reported latency and reported cost. The fake's usage fields are shown only to expose call-count changes; they are not real-call measurements.

## Starter versus mine, on the same model

| Metric | Starter (fake) | Current (fake) |
|---|---:|---:|
| Fields correct | 75/288 (26.0%) | 75/288 (26.0%) |
| Missed reviews (13 labeled review cases) | 13/13 | 0/13 |
| Unnecessary reviews (11 labeled clean cases) | 0/11 | 10/11 |
| Processing failures | 0/24 | 0/24 |
| LLM calls per document | 2 | 1 |
| Reported fake cost per document | ₹0 | ₹0 |
| Fake call-latency p50 / p95 | 10 / 10 ms | 5 / 5 ms |
| Real provider cost / end-to-end p50 and p95 | Not measured | Not measured |

The apparent routing improvement is not evidence that recall improved: the fake repeats invoice `SIS/26-27/0042`; after the first row, deterministic duplicate detection flags the repeated fake invoice. That produces 10 artificial unnecessary reviews. Similarly, its identical extraction causes the low field score. The 5 ms is hard-coded per fake call, not observed network or end-to-end latency. A live cost comparison and the CTO's ₹1.50/document and 10-second p95 targets remain unknown.

## Labels I disagree with

I do not overturn any dev `needs_review` label on the evidence supplied. The suspicious-content cases include an explicit instruction to bypass review (`dev_012`) and executable HTML with a data-exfiltration handler (`dev_013`); `dev_008`'s printed total is ₹900 above its line sum plus tax; the other review labels map to the written bank, duplicate, GSTIN, vendor-age, tax-type or foreign-currency rules.

One policy choice worth revisiting is `dev_011`'s `vendor_new` review: a blanket 90-day window can delay legitimate invoices from a vendor that has already completed onboarding, which matters given the Controller's 45-day MSME payment concern. The record does not establish that onboarding controls are complete, so I retain the label. As a sensitivity only, if Finance removed this one review label, expected review cases become 12: the fake starter would miss 12/12 instead of 13/13; the current fake would still miss 0/12 but have 11 unnecessary reviews instead of 10/11. Field accuracy stays 75/288 because routing is not one of its fields.

## Failure analysis

The starter's dominant measured failure is routing: its canned `requires_review=false` misses all 13 labeled issues. The current fake's dominant routing error is synthetic duplicate over-review after it repeats one invoice. Neither run measures how a real model handles OCR variation, injection, foreign amounts or bank changes. The unchanged field score also omits bank data and line items, so it cannot validate the fixes to those paths. The dev set is intentionally problem-rich: 13/24 (54%) are labeled for review, versus 26/200 (13%) in the October hand-checked sample. Do not extrapolate its review rate or fake false-positive rate to production.

## How much to trust these numbers

Trust the 24-document run only for confirming that both code versions execute offline and for demonstrating how the old scorer works. The fake produces identical output on every run, so there is no model variance and its cost/latency values are not representative. A 24-document, deliberately enriched dev set is not a production estimate. No provider invoice, actual request latency, realistic OCR mix, or independently held-out model evaluation was available.

## My recommendation

**No** to routing all 3,000 monthly documents through Ledgerline for production next month. Meridian's production mix is about 70% OCR, 20% email and 10% e-invoice JSON; 40% (about 1,200/month) are under ₹10,000, while the 13% problem rate suggests roughly 390 genuine review cases monthly. The CFO's no-touch request for small invoices conflicts with AP policy's human-approval requirement; amount alone is not authorization to pay.

An unnecessary review costs about ₹85 plus delay: 390 genuine reviews would represent roughly ₹33,150/month of review work. Among the estimated 2,610 clean documents, each 1 percentage point of false-positive rate adds about 26 reviews or ₹2,219/month; reviewing every clean invoice would cost about ₹221,850/month. But one missed bank-change review can expose Meridian to a full invoice payment; Farhan cited a ₹3.8 lakh loss, roughly the cost of 4,471 manual reviews. That is why the fake's zero misses cannot justify rollout.

I would reconsider after a DPO-approved, real-provider shadow evaluation on a representative, manually labeled holdout, with no leaked examples, failed documents counted, measured billing and end-to-end p95, and demonstrated performance against the ₹1.50 average and 10-second p95 targets. Finance must also resolve whether to amend the no-automatic-approval policy, and reviewers need source evidence for extracted values before operational use.
