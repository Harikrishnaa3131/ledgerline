# My first hour

## What I think is going on

The handover's “94%” is field extraction accuracy, not proof of safe routing. The eval skips exceptions, potentially inflating it. Worse, model `requires_review` controls routing while deterministic checks are warnings; prompts cannot reliably enforce payment rules. Cost is also suspect: the app estimates from token counts and local prices, while the CTO cites the provider bill. I need to compare calls, rates and currency conversion.

## The risks I suspect, most serious first

1. A fraudulent bank change may pass without callback verification; policy only flags it for review.
2. Duplicate approvals may create duplicate payments, as AP reports.
3. Wrong GSTIN, tax type or totals risk fraud and tax exposure.
4. Hostile invoice instructions may manipulate extraction or routing.
5. Vendor data, including bank details, may leave Meridian.
6. Misrouting, late payments and untracked spend/latency create operational risk.

## My plan for the time I have

First reproduce the starter and trace routing, approvals and eval. Spend two hours on deterministic policy enforcement and payment idempotency with tests; one hour on disputed rulings behind off-by-default flags; one hour on an honest eval counting failures and measuring review misses, cost and latency. Use the last two hours for Option A: evidence-linked review and safe server-side approval, prioritizing the core path. Skip fine-tuning and unsupported rollout claims.

## What I would ask Meridian

Does the CFO's no-touch route under ₹10,000 override policy's human approval requirement, or stay off pending a policy change? Should bank changes be blocked for callback, as Farhan asks, though policy only requires review and the vendor master has no phone number? May AI “correct” an OCR-read GSTIN, or must it match the printed value? Does the ₹5 lakh, two-approver threshold remain, and how does it combine with the two approvals required for foreign invoices?
