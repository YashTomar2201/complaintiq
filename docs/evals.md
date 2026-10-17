# AI Triage Evaluation (Phase 6)

How accurate is the AI triage compared with a human? Model: `gemini-3.5-flash-lite` (free tier). Reproduce: `python -m evals.run_eval v1 v2`.

## 1. Test design
- **Gold set:** 100 complaints with narratives, spread over products (credit card 30, checking/savings 25, credit reporting 20, debt collection 12, vehicle loan 8, money transfer 5), duplicates removed. Source list: `evals/gold_set.csv`.
- **Labels:** made by the project owner alone, from scratch, in an Excel workbook, using the same rubric the AI is given (a test checks the two texts match). No AI was used for the labels. `evals/gold_labels.csv`.
- **What the human labeled:** root cause (10 categories), severity (1-5), vulnerable consumer (yes/no).
- **Limits:** one labeler (no inter-annotator agreement measured); 100 complaints, so one complaint = one percentage point.

## 2. Results: prompt v1 to prompt v2
| Metric | v1 | v2 |
|---|---|---|
| Root cause accuracy | 80.0% | **84.0%** |
| Severity exact match | 66.0% | **71.0%** |
| Severity within +-1 | 95.0% | **97.0%** |
| Severity mean absolute error | 0.40 | **0.33** |
| Critical (human 5) rated 3 or lower by the AI | 3 of 14 | **0 of 14** |
| Human severity >= 4 also rated >= 4 | 77.4% | **96.8%** |
| AI rated lower than human / higher than human | 25 / 9 | 17 / 12 |
| Vulnerable consumer: recall | 87.0% | **100.0%** |
| Vulnerable consumer: precision | **83.3%** | 74.2% (8 false alarms, was 4) |
| Valid structured output | 100% | 100% |
| Tokens per complaint (in / out) | 1,319 / 109 | 2,041 / 105 |
| Cost per complaint at paid-tier list price | $0.00067 | $0.00088 |

Real cost on the free tier: $0.

## 3. Error analysis of v1 (what the 50 imperfect complaints had in common)
1. **Severity was biased low:** the AI was lower than the human on 25 complaints and higher on 9. Largest cell: human 3 vs AI 2 (13 cases). 3 of the 14 critical complaints were rated 3, with a further 5 rated 4.
2. **Credit reporting over-chosen:** the AI picked it 28 times, the human 22. Five errors were debt-collection or identity-theft complaints that merely mention a credit report.
3. **Customer service over-chosen:** AI 3 times, human 0. The human picks the underlying problem (fee, account restriction, payment).
4. **Unauthorized transactions:** the AI under-rated money-lost cases and did not always treat the account holder as a victim of fraud, so it missed some severity 5.
5. **Vulnerable consumer was fine** (7 errors in 100). My first guess that v1 over-flags it was **wrong**; reading 20 outputs misled me, the labeled data did not.

## 4. What changed in v2 (prompt text only; schema, model and rubric lines unchanged)
- Tie-breaker rules for root cause (identity theft or debt collector beats "credit report"; customer service only if staff behaviour is the main complaint; rewards and terms disputes go to "other").
- Severity clarifications: when torn choose the higher level; any unresolved money dispute is at least 3; money lost and not returned is at least 4; unauthorized transactions or identity theft make the consumer a fraud victim (vulnerable); legal-sounding claims with no concrete harm are 1-2.
- Five new short examples written for the prompt. **Leakage guard:** two draft examples were too close to specific gold complaints and were replaced before the run.

## 5. How much to trust the improvement
- **Root cause:** v2 fixed 11 complaints and broke 7 (net +4). **Severity exact:** fixed 15, broke 10 (net +5). With 100 items these net gains are small and could partly be noise.
- **Clearer improvements:** critical complaints missed (3 to 0), the low-severity bias (25 to 17), vulnerable recall (87% to 100%).
- **Regressions:** vulnerable false alarms doubled (4 to 8), `fees_interest` recall fell (0.73 to 0.64; three fee/APY complaints went to "other"), `billing_error` and `unauthorized_transaction` recall fell (1.0 to 0.80 and 0.86). "Improve once" was the rule, so these are left for a v3.
- **Optimism warning:** I wrote v2 after studying errors from these same 100 complaints. Root cause got better on complaints 51-100 (74% to 86%) but slightly worse on 1-50 (86% to 82%), so the gain is not uniform. Treat 84% as an upper bound until it is confirmed on **fresh complaints labeled by a human** (recommended: 30 more).

## 6. Is it good enough for the customer?
- **For assisted triage with a human approving everything: yes.** Severity is within one level 97% of the time, none of the 14 critical complaints were rated 3 or lower, and the vulnerable flag never missed one (at the price of 8 false alarms in 100, which a reviewer clears quickly).
- **Targets from the discovery doc:** root cause 84% (target >= 80%, met); severity within +-1 97% (met), but severity **exact** match is 71%, below 80%; cost $0.00088 per complaint (target < $0.01, met).
- **Not good enough to act without a person:** about 1 in 6 root causes is wrong and severity is exact only 7 in 10 times.

## 7. Next steps (not done yet)
- A v3 prompt aimed at the vulnerable false alarms and the fee/APY complaints, tested on a fresh 30-complaint human-labeled holdout.
- Regulation-suggestion check on 20 complaints (Phase 7) and CI eval on a 30-complaint subset (Phase 9).
