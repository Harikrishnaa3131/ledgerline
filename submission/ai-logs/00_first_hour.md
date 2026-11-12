# First-hour AI session transcript

_Best-effort record of this first stretch in the available chat. File contents and tool results are summarized rather than reproduced verbatim. No secrets were present._

## User

Write `submission/FIRST_HOUR.md` in my own words, under about 300 words. Cover what seems wrong with the pipeline, ranked risks, a plan for the six available hours, and specific questions about conflicts between `AP_POLICY.md` and `STAKEHOLDER_THREAD.md`. Save the AI session transcript in `submission/ai-logs/00_first_hour.md`.

## Assistant

I read the first-hour template, AP policy, stakeholder thread, handover, architecture, output contract, and challenge README. The written policy says every invoice needs a human approval and identifies bank changes, duplicates, GSTIN/tax/totals errors, suspicious content, foreign currency, and processing failures as review conditions. The CFO proposes straight-through processing under ₹10,000 and AI repair of garbled GSTINs; AP requests verified callbacks for bank changes and reports duplicate payment entries; the Finance Controller notes that callback phone numbers are not in the vendor master.

I inspected `pipeline.py`, `validation.py`, `eval/run_eval.py`, and `llm/pricing.py`. In the pipeline, the model's `requires_review` and `review_reasons` determine routing, while deterministic checks are stored as warnings. The eval reports field accuracy and skips documents that throw exceptions. Cost is estimated using a local price map and token counts. These observations informed the initial assessment, but I did not run the pipeline, reproduce a metric, or validate the reported payment race.

I then drafted `submission/FIRST_HOUR.md` as an initial, pre-fix assessment, ranking fraud and duplicate-payment risks first; proposing a six-hour plan centered on deterministic rules and Option A; and listing the policy conflicts that need a ruling.
