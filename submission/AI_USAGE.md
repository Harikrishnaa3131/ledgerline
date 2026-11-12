# How I worked with AI

## Tools and models

I used Copilot SDK in VS Code. The local session usage record identifies the assistant model as `gpt-6-luna` (131 model calls in this session). For Ledgerline pipeline runs and tests I used `LLM_PROVIDER=fake`; no direct Anthropic/OpenAI provider call was made because no provider key was configured. The fake's repeated extraction and synthetic usage are not model-quality, provider-cost or latency evidence. I used PowerShell, pytest, Ruff, and the existing Vite/TypeScript build; I added no dependencies.

## How I set up context

I read the AP policy, stakeholder thread, product brief, handover, architecture and output contract, then followed the relevant pipeline, validation, evaluation, API and UI code. I did not create `CLAUDE.md`, `AGENTS.md`, `.cursorrules` or other persistent AI context files. I did not use a planning mode or delegate work.

## My workflow

I used the assistant to trace code paths, draft focused implementation changes and identify test cases. I chose the policy interpretations and rollout recommendation, and checked changes against the written policy, fixture data and tests. I treated fake-provider measurements as execution checks only, reviewed generated text for claims not supported by evidence, ran offline tests and Ruff, built the frontend, and generated the final JSONL artifacts with the fake provider.

## Where the AI was wrong

1. **Overbroad buyer-GSTIN extraction:** an early implementation treated a nearby “recipient” GSTIN as the buyer's. The disputed USD invoice exposed the false match. I narrowed extraction to Buyer/Bill To context and added a regression test. See the Part 2 section of [`01_parts_1-6.md`](ai-logs/01_parts_1-6.md) and `disp_03` in [`RULINGS.md`](RULINGS.md).
2. **Misleading source ambiguity:** the first evidence matcher counted overlapping variants such as “invoice” and “tax invoice” as two occurrences. A focused test showed that one printed phrase was being called ambiguous; I merged overlapping spans and added a regression test. I also made bank-account evidence require a labeled account context rather than accepting an unlabeled substring. See Part 4 in [`01_parts_1-6.md`](ai-logs/01_parts_1-6.md).
3. **Policy/code mismatch in the callback proposal:** an earlier draft said bank changes should be blocked until callback, although the implementation only flags them for review and AP_POLICY does not mandate a callback. I corrected the response: the callback hold is a proposed policy change, not an implemented control. See Part 5 in [`01_parts_1-6.md`](ai-logs/01_parts_1-6.md).

## What I deliberately didn't delegate, and why

I handled the end-to-end policy and code trace directly because the decision depends on comparing the same rules across extraction, routing, approvals and evaluation. I did not send Meridian's invoice data or repository content to an external model provider. I also did not ask a second agent to review this work.

## Time

Approximately two hours elapsed for the project work in this Copilot session; this is an estimate, not time-tracker data, and is under the eight-hour limit. Work covered the initial assessment, deterministic backend fixes and tests, disputed rulings, evaluation, the evidence-linked reviewer workflow, stakeholder responses and final artifacts.

## Transcripts

- [`00_first_hour.md`](ai-logs/00_first_hour.md) — first-stretch record.
- [`01_parts_1-6.md`](ai-logs/01_parts_1-6.md) — best-effort continuation record for this session.
- [`01_session_context_export.json`](ai-logs/01_session_context_export.json) — redacted, bounded session-context export.

The VS Code session-context export exposes bounded excerpts and omits tool-result payloads; these files therefore identify themselves as a curated, secret-redacted record rather than a verbatim dump of every tool interaction. The export was checked for common API-key patterns; none were found.
