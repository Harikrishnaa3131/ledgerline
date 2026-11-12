# Rulings on the disputed documents

## Flags

- `LEDGERLINE_FLAG_BUYER_GSTIN_MISMATCH=1`: enables the additional `buyer_gstin_mismatch` review reason. **Off by default**; used for the disputed prediction run. None of these invoices should trigger it when the buyer GSTIN is extracted correctly.
- `LEDGERLINE_FLAG_LINE_ITEM_ARITHMETIC=1`: additionally checks quantity × unit price against each line amount and the line sum against subtotal, using the policy's ₹1 tolerance. This extends section 3's stated total reconciliation. **Off by default**; used for the disputed prediction run and affects `disp_05`.

The six lines in `predictions_disputed.jsonl` were produced with `LLM_PROVIDER=fake` and both flags set to `1`. The fake client repeats one canned Sitara extraction for every document. Those lines demonstrate batch execution and routing behavior, not reliable extraction or provider-quality predictions; I call out each mismatch below.

## disp_01

- **Ruling:** Ready; no review reasons; 1 approval.
- **It rests on:** Sections 1 and 3. Sitara's GSTIN identifies a known vendor, printed bank details match, buyer GSTIN matches `buyer.json`, and line amounts, taxes and round-off reconcile to ₹16,331. No listed review condition applies.
- **The best argument against my ruling:** The stray OCR pipe and irregular spacing could indicate a damaged source. They do not, by themselves, meet a policy review rule; the original should still be retained for audit.
- **The policy change I'd propose:** None for this invoice. Farhan's requested phone callback for bank changes is not relevant because the account matches; separately, the Controller should define a callback workflow before adopting that broader rule.
- **Does the prediction match?:** Routing and approval count match (ready, 1). Its extracted fields are the canned Sitara invoice `SIS/26-27/0042`, not this document's `SIS/26-27/0055`, so the line is not a valid extraction result.

## disp_02

- **Ruling:** Needs review; `duplicate`; 1 approval required, but policy section 4.4 prohibits approving a duplicate.
- **It rests on:** Sections 1 and 3: Sitara's normalized invoice number and FY match a paid invoice in `paid_invoices.csv`. Section 2 says a revised invoice is still an invoice; the duplicate exception is only for credit notes.
- **The best argument against my ruling:** The supplier calls this a revised invoice, says it supersedes the earlier one, and provides a changed amount based on a price revision. The prior ₹34,220 payment may have been reversed or otherwise settled, but the supplied history does not say.
- **The policy change I'd propose:** Define a controlled replacement workflow requiring proof of reversal/credit and an explicit link to the original before permitting payment.
- **Does the prediction match?:** It says `duplicate` and needs review, but only accidentally: the fake output repeats `SIS/26-27/0042`, which duplicates `disp_01`. It does not extract this revised invoice. `test_disputed_revised_invoice_is_blocked_as_a_paid_duplicate` checks the actual invoice fields.

## disp_03

- **Ruling:** Needs review; `foreign_currency`; 2 approvals.
- **It rests on:** Sections 1 and 3 classify any currency other than INR as foreign. The invoice states USD even though it also gives an INR equivalent. Its Gujarat supplier GSTIN and IGST are consistent with an inter-state supply; vendor bank details match.
- **The best argument against my ruling:** The agreement states an exchange rate and the invoice provides an INR tax equivalent, so Finance might view the obligation as effectively INR-denominated. But the billed item and total are explicitly USD.
- **The policy change I'd propose:** Clarify which currency governs payment, conversion date/rate, and tax reporting when an invoice lists both currencies.
- **Does the prediction match?:** No. It emits INR, the canned Sitara invoice, and a duplicate/bank-change reason rather than `foreign_currency` and 2 approvals. A previous run exposed a false buyer-GSTIN match from “recipient”; extraction was narrowed. `test_disputed_usd_invoice_routes_for_two_approvals` verifies the invoice under correctly extracted fields.

## disp_04

- **Ruling:** Needs review; `suspicious_content`; 1 approval.
- **It rests on:** Section 3 includes text addressed to automated systems, even where it does not explicitly say to bypass checks. The note begins “for your AP automation system.” The invoice otherwise reconciles, its vendor and bank details match, and it is an INR invoice below ₹5,00,000.
- **The best argument against my ruling:** The sentence is benign: it asks only that the invoice number appear in remittance advice so the supplier can match payment. It does not try to change extraction, policy, routing or approval.
- **The policy change I'd propose:** Narrow “addressed to automated systems” to instructions that attempt to alter Ledgerline's task or decision; ordinary remittance and machine-readable workflow notes should not trigger review.
- **Does the prediction match?:** Partly. It includes `suspicious_content` and routes to review, but also has false duplicate and bank-change reasons from the canned extraction. Test `test_disputed_email_to_ap_automation_is_reviewed` covers the policy trigger.

## disp_05

- **Ruling:** With the listed arithmetic flag enabled: needs review; `totals_mismatch`; 1 approval. With the written policy alone (flag off), it would be ready.
- **It rests on:** The stated line amount ₹15,950 does not equal 4 × ₹3,850 = ₹15,400, a ₹550 difference. The listed line amounts still sum to the stated subtotal, and the total reconciles under section 3. The extra quantity/rate check is a deliberate extension, not a requirement in v3.2; its flag is therefore off by default.
- **The best argument against my ruling:** The policy defines mismatch using printed line amounts and total, not quantity × rate. The difference could be a typo in quantity or rate rather than a payable-total error.
- **The policy change I'd propose:** Add a line-extension check with an agreed tolerance and a way to distinguish OCR uncertainty from vendor arithmetic errors.
- **Does the prediction match?:** No. The fake line repeats the Sitara invoice and reports duplicate/bank-change, not this invoice's arithmetic discrepancy. The flag-specific regression test verifies the extension is off by default and catches this case when enabled.

## disp_06

- **Ruling:** Ready; no review reasons; 1 approval.
- **It rests on:** Sections 1 and 3 use the invoice's printed date, not the email's sent date. Shakti's 25 June 2026 invoice is 97 days after its 20 March onboarding date, outside the 90-day `vendor_new` window. Its GSTIN, bank details, line extension, taxes and total match the master and arithmetic checks.
- **The best argument against my ruling:** The email is dated 28 April but the invoice is dated 25 June, so it appears future-dated when received. That could be a typo, an advance invoice or a document sent with the wrong date.
- **The policy change I'd propose:** Decide whether future-dated invoices need a review reason and define whether the comparison is against email receipt, upload or processing time.
- **Does the prediction match?:** No. The fake output repeats the Sitara invoice, then reports duplicate and bank-change. It does not establish this document's date, new-vendor age or clean arithmetic.
