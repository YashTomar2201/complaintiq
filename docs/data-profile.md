# Data Profile (raw Capital One data, Aug 2024 – Aug 2026)

Profiled the 66,963-row narratives archive extract and compared it with the live CFPB bulk CSV and API. This drives the cleaning rules in Phase 3 and the design of Phase 2.

## 1. Sources and how they differ
| Source | Rows (Cap One) | Narrative | Notes |
|---|---|---|---|
| Narratives archive (FOIA, 15 zips) | 66,963 (2024-08-01 → 2026-08-31) | yes (26,157) | Snapshot; status fields go stale |
| Bulk CSV (`complaints.csv.zip`) | 70,521 since 2024-08 (174,780 all-time) | **no** | Fresher: 3,613 newer rows not in the archive (from 2026-06-15 to 2026-10-14) |
| Live API | same as bulk | **no** | JSON, snake_case names, ISO timestamps (`2026-10-14T04:03:38.000Z`) |

- Of the 66,963 archive IDs, 66,908 are also in the bulk CSV; **55 archive-only IDs** (likely removed or re-published, to inspect).
- Product, issue, state, tags, dates agree between sources. **610 rows differ in `Company response to consumer`** (the archive says "In progress", the bulk file has the final answer). So structured fields should be refreshed from the bulk file and narratives joined from the archive by `Complaint ID`. This is the reason for upsert logic.

## 2. Cleaning rules (by column)
| Column | Finding | Rule |
|---|---|---|
| Complaint ID | unique, 7–8 digits, no duplicates | keep as TEXT primary key |
| Date received / sent | all ISO `YYYY-MM-DD`, no unparseable, none sent before received; lag median 0 days, max 159 | cast to DATE; add `year_month`, `week` |
| Product | 11 values; 6 are 99% of rows (Mortgage 13, Student loan 9, Prepaid 66 are tiny) | keep; group tiny ones as "Other" in charts |
| Sub-product | 48 values; **"I do not know" = 3,201** | map to NULL/"Unknown" |
| Issue / Sub-issue | 70 / 158 values, clean casing; Sub-issue blank 1,173 (1.8%) | trim; blank → NULL |
| Narrative | blank in 60.9%; `Phone`, `Postal mail`, `Referral` channels **never** have one; only Web (41%) | blank → NULL; `has_narrative` flag |
| Company public response | **100% blank** | drop |
| Company | single constant value | drop from models (keep in raw) |
| State | 58 values: 50 states + DC + territories + `UNITED STATES MINOR OUTLYING ISLANDS` (7); **192 blank (0.3%)** | keep as is; blank → NULL; 141 of those blanks still have a ZIP (could infer state from ZIP prefix, not planned) |
| ZIP code | text already; 58,153 full 5 digits, **8,085 masked like `604XX`**, 649 fully `XXXXX`, 76 blank; no lost leading zeros here | keep as TEXT; add `zip3` (first 3 digits, NULL when masked to fewer than 3); fully masked → NULL |
| Tags | blank 89.2%; 4 values incl. combined "Older American, Servicemember" | split into booleans `is_older_american`, `is_servicemember` |
| Submitted via | Web 64,046, Referral 1,366, Phone 1,174, Postal mail 377 | keep |
| Timely response? | Yes 66,960, No 3 | → boolean (≈100%, near-constant) |
| Company response | Closed with explanation 82%, non-monetary relief 12%, monetary relief 4.4%, **In progress 692** (625 from Aug 2026) | keep; "In progress" are not final → exclude from relief-rate denominators |

## 3. Narrative text facts (for the AI phases)
- 26,157 narratives; length min 31, median 729, p99 ≈ 5,400, max 32,503 characters → **truncate to ~4,000 characters** before the LLM to bound cost.
- Already CFPB-masked: 18,885 contain `XXXX` (names/places/dates), 5,632 contain `XX/XX/XXXX`. **Dollar amounts are wrapped like `{$123.45}`** (8,238 narratives) — easy rule-based extraction for the money field, and a way to cross-check the LLM.
- No emails or phone numbers found, all ASCII, no stray whitespace. Newlines in 9,370 (collapse to spaces). Presidio is still run as a safety net.
- 70% mention "Capital One" by name (name stays; it is the company, not PII).
- **Narrative availability falls over time**: ≈50% (2025) → 25% (Q2 2026) → 12% (Jul) → 0% (Aug 2026). Sampling for AI must therefore draw from complaints dated before Aug 2026.

## 4. Duplicate / templated narratives
- 135 groups of identical narrative text (1,191 rows). **One template appears 576 times** (893 duplicate-text rows are in **January 2025**): a copy-pasted complaint about a failed direct deposit ("technical issues"), filed from many states. These are different customers, not duplicate rows.
- Implications: (a) do **not** drop them as duplicates, (b) for the AI sample and the 100-item gold set, **deduplicate by narrative text** so one template doesn't dominate, (c) this is the Jan 2025 systemic event (7,601 complaints; sub-issue "Deposits and withdrawals" 3,278) that Phase 7 clustering should detect.

## 5. Data quality headline numbers
- Missing: narrative 60.9%, tags 89.2% (means "no tag"), sub-issue 1.8%, State 0.3%, ZIP 0.1%, fully/partially masked ZIP 13.1%.
- No duplicate IDs, no duplicate rows, no bad dates.
- Biggest real "messiness": masked ZIPs, "I do not know" sub-product, stale response status, templated narratives, narrative availability collapsing over time.

## 6. Consequences for the plan
1. **Phase 2:** load the archive into `raw_complaints` (narratives + structure), then upsert the bulk CSV to refresh status and add the 3,613 newer rows (no narrative). Store `source` and `ingested_at`. Incremental load later via the API (no narrative). The API date format differs and must be normalized.
2. **Phase 3:** apply the cleaning rules above; ZIP matching to the fake CRM must use `zip3`, and the planted matches must be limited to complaints with an unmasked ZIP prefix.
3. **Phase 4:** exclude "In progress" from relief-rate KPIs and show a note that on-time % is ~100%.
4. **Phase 5/6:** sample AI inputs from deduplicated narratives dated before Aug 2026; extract `{$...}` amounts by rule to check the LLM's money field.
