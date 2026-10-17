# Decision Log

Format: Decision · Reason · Alternatives · Trade-offs · Interview explanation

## Phase 0 — Setup
**Decision:** Build directly in `D:\FDE\CFPB_complaint_intelligence` (project root = repo root) with a Python 3.11 venv in `.venv`.
**Reason:** System default Python is 3.10; the guide requires 3.11+, and 3.11 was installed via the `py` launcher.
**Alternatives:** Upgrade global Python; use a `complaintiq/` subfolder. **Trade-offs:** none significant.
**Interview:** "I pinned the project to a venv so it's reproducible regardless of what's installed globally."

**Decision:** Use the Anthropic SDK as the LLM provider (`claude-haiku-5-5` for bulk triage, `claude-sonnet-5-5` for harder tasks).
**Reason:** Guide's suggested stack; cheap model for bulk, stronger one for reasoning. **Alternatives:** other providers. **Trade-offs:** vendor lock-in is small since calls are isolated in `src/ai/`.
**Interview:** "Cheap model for volume work, stronger model only where reasoning matters, to control cost."

**Note:** Docker is not installed yet (needed in Phase 9).

## Phase 1 — Discovery
**Decision:** Use the CFPB FOIA Reading Room "Narratives Archive" (15 zip files, Aug 2024–Aug 2026, 676 MB) as the main data source instead of the live API / bulk CSV.
**Reason:** CFPB stopped publishing narratives (announced 14 Aug 2026). The API and bulk CSV have no narrative column; the archive still has 26,157 Capital One narratives (39.1% of 66,963 complaints).
**Alternatives:** synthetic narratives (LLM-written; not real), structured fields only (weak AI story). **Trade-offs:** narratives thin out after 2025 and are 0% for Aug 2026; archive is static, so newer complaints come from the live API without text.
**Interview:** "The source changed under me mid-project, so I verified what was actually available, found the official archive, and adapted the pipeline instead of faking data."

**Decision:** Keep the on-time KPI but do not lead with it.
**Reason:** Measured 99.995% timely (3 late of 66,963), so it carries almost no signal.
**Interview:** "I checked the data before promising a metric; the on-time rate was nearly constant, so I focused on volume, relief rate and issue trends."

**Decision:** Treat the Jan 2025 spike (7,601 complaints vs ~2,300 normal) as a test case for risk alerts.
**Reason:** 4,474 "Managing an account" complaints on checking/savings in one month is a genuine systemic event.

## Phase 1 (addendum) — Data profiling
**Decision:** Combine two sources: narratives archive (text) + bulk CSV (fresh status and newest rows), joined by `Complaint ID`.
**Reason:** 610 complaints are "In progress" in the archive but closed in the bulk CSV; 3,613 newer complaints exist only in the bulk CSV. Neither source alone is complete.
**Alternatives:** archive only (stale status, misses newest). **Trade-offs:** two sources to maintain; newest complaints have no narrative.
**Interview:** "No single source was complete, so I reconciled two by ID and let the fresher one win for status fields."

**Decision:** Keep templated duplicate narratives in analytics, but deduplicate by text for AI sampling and the gold set.
**Reason:** One template appears 576 times (Jan 2025 direct-deposit event); they are different customers, but would dominate a random sample.
**Interview:** "Duplicates aren't always errors; a repeated text is a signal of a systemic issue, but it biases evaluation samples."

## Phase 2 — Ingestion
**Decision:** One `raw_complaints` table keyed on `complaint_id`; every load is an UPSERT; the narrative is protected with `COALESCE` so a source without narratives can never erase one.
**Reason:** Re-running gave 0 new / 0 updated for all three sources (tested); bulk refresh correctly found 610 status changes and 3,613 new rows, matching the Phase 1 profile exactly.
**Alternatives:** truncate-and-reload (simple but destroys history and is slow), insert-only (duplicates). **Trade-offs:** comparing all columns on each load costs a little time (full archive load ≈ 85 s).
**Interview:** "The pipeline is idempotent: I ran every load twice and the row counts and change counts were identical; a different source can never overwrite good data with blanks."

**Decision:** Filter the bulk CSV by raw line before parsing.
**Reason:** The bulk file has 18.5M rows but no narratives (so no multi-line rows); string-filtering lines cut the run to ~30 s versus ~10 min with pandas chunks.
**Trade-offs:** relies on no embedded newlines; guarded by a post-parse exact company-name check.

**Decision:** API used only for small incremental loads (watermark = latest `date_received` minus 7 days); it refuses (and says to use `bulk`) if more than 10,000 results are needed.
**Reason:** The API caps paging at 10,000 results and returns no narratives. The 7-day overlap catches updated complaints.

**Decision:** Dates normalised to `YYYY-MM-DD` and blanks stored as NULL at load time; everything else stays raw text for Phase 3 to clean.
**Reason:** Needed for a consistent watermark and for change detection; the API returns full timestamps, the CSVs return dates.

**Finding:** 55 archive complaints (all "In progress", Jul–Aug 2026, no narrative) are absent from the newer bulk file (likely withdrawn/not yet published). Kept as-is; they carry `source='archive'`.

**Window:** "last 24 months" = 2024-08-01 onwards, matching the archive start. Table now spans 2024-08 to 2026-10 (October partial).

## Phase 3 — Cleaning, modeling, messy CRM
**Decision:** Keep ZIP as TEXT in three columns: `zip5` (full), `zip3` (prefix, usable even when the CFPB masks the last digits), `zip_masked`.
**Reason:** 12.5% of ZIPs are masked (`604XX`); dropping them would lose location for ~8,700 complaints, while the 3-digit prefix still supports matching and state-level analysis.
**Interview:** "ZIP is an identifier, not a number; I kept what the privacy masking still allows me to use."

**Decision:** Build clean tables with SQL (`models.sql`) rebuilt from raw on every run; keep Python only for things SQL does badly (CRM name parsing, fuzzy cleaning).
**Reason:** One saved definition feeds dashboard, tests and reports; a rebuild is safe and takes seconds.

**Decision:** The planted answer key lives in separate files (`crm_truth*.csv`) that only the evaluation reads.
**Reason:** If the matcher could see the answers, its precision/recall would be meaningless (same principle as hand-labelled gold data in Phase 6).

**Decision:** Matching rule = required agreement (state, zip3, product, opened before) + scored extras (exact ZIP, recent opening); one customer ↔ one complaint; ties go to review. Strict setting (score ≥ 8) chosen.
**Reason (numbers):** loose 1.3% precision / 97.3% recall; strict 83.7% precision / 29.0% recall. A wrong link to a customer is costlier than a missed link.
**Alternatives:** looser rules (too many false links), fuzzy name matching (impossible: CFPB has no names). **Trade-offs:** recall is low; ambiguous links need a human.
**Interview:** "Stricter rules raised precision from 1% to 84% and cut recall from 97% to 29%; I chose precision because linking the wrong customer is worse than missing one, and routed ties to review."

**Decision:** Duplicate CRM records merged on last name + first initial + ZIP + product + open date, with nickname and "LAST, FIRST" normalisation.
**Reason:** merged 5,100 records into exactly the true 4,700 people.
**Caveat:** a simulation assumption (planted customers open the account 30–540 days before complaining) drives the timing score; real timing rules would come from the customer.

**Fix to my own work:** an early version also treated a customer's other nearby complaints as wrong matches; adding the one-customer-one-complaint rule changed precision from 1.7% to 39.8% at the same score cutoff, at the cost of recall.

## Phase 1-3 review improvements
**Decision:** Add narrative helper columns to `complaints` now (`is_first_copy`, `narrative_copies`, `amounts_usd`, `narrative_chars`).
**Reason:** The Phase 1 finding (one template appears 578 times) must be enforced in code, not only written in a note; 25,078 of 26,157 narratives are unique. `{$..}` amounts give a rule-based cross-check for the LLM's money field.
**Interview:** "I turned a finding into a column so every later phase samples fairly without remembering a rule."

**Decision:** Flag complaints that vanish from the newest bulk file (`missing_from_bulk`, 55 rows) rather than delete them.
**Reason:** We cannot tell whether they were withdrawn or are just delayed; keeping and flagging preserves information and lets reports exclude them.

**Decision:** Test the cleaning SQL with a small hand-made raw table (6 tests) instead of the real data.
**Reason:** Tests then run anywhere (including CI without the 70k-row database) and show exactly what each rule should do.
