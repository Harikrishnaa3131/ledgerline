# Reflection

## Three things I learned

1. **The handover's 94% is not a routing-safety score.** I learned this by reading the eval implementation and running the starter on all 24 dev documents. It compares 12 fields, can skip failures, and includes labeled examples in the prompt. The offline fake scored 75/288 fields (26%), but because it repeats one canned response, that says nothing about a live model's accuracy.
2. **Exact arithmetic needs exact storage too.** Decimal calculations alone were not enough: the schema still used SQLite `REAL`, despite the architecture describing paise. Tracing persistence and API consumers led to integer-paise storage and migration tests.
3. **A source highlight must be honest about uncertainty.** Alternative text formats can overlap, the same value can appear in unrelated text, and Python's character offsets differ from browser string offsets for some Unicode. Tests exposed cases where a plausible-looking highlight would have been misleading; the UI now reports ambiguity or no match instead.

## The decision I'm least sure of

The line-item arithmetic extension is my least certain call. Disputed invoice `disp_05` says 4 × ₹3,850 but lists ₹15,950; the ₹550 difference is concerning, yet AP policy v3.2 only reconciles listed line amounts, taxes, round-off and total. I left `LEDGERLINE_FLAG_LINE_ITEM_ARITHMETIC` off by default. I would reconsider if a Controller-approved sample shows that line amount is authoritative (for example, because of discounts or pack pricing), or if purchase orders and vendor confirmations establish that quantity × unit price must always match.

## What I'd do with one more week

1. Run a DPO-approved, capped shadow evaluation on a representative, independently labeled set. Compare starter and current code on the same real provider, with bank data protected; report routing misses, false reviews, actual billing and end-to-end p50/p95. Keep production routing off until the results meet agreed thresholds.
2. Manually exercise the reviewer workflow with AP, including hostile documents, ambiguous source matches, repeated clicks, two-person approval and rejection; add concurrency and identity controls based on that review.
3. Work with the Controller and DPO on a trusted phone source and auditable callback/hold workflow for bank changes before implementing the proposed policy change.
4. Review the flag-gated line-item rule against real purchase orders and invoices, then let Finance decide whether to adopt it.
5. Design a versioned, validated policy-configuration path so routine Controller-approved changes do not depend on editing prompts or bypassing code review.

## What I cut and why

I did not make live provider calls: no API key was configured, and the starter would send bank data externally. I cut model benchmarking, provider fallback and fine-tuning because fake-provider numbers cannot support a quality or cost decision. I did not implement Farhan's callback block because the vendor master has no trusted phone number and AP_POLICY does not require a callback. I also skipped an interactive browser check because port 8000 was already occupied; backend tests and the frontend production build passed instead.
