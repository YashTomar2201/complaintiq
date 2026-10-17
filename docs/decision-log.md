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

## Phase 4 — Dashboard
**Decision:** One SQL view, `v_dashboard_facts` (grain: day x product x state x issue x response), feeds every KPI, chart and insight; a test checks it agrees with the Phase 3 `v_monthly_trends` view.
**Reason:** If each chart computed its own numbers they could disagree and the customer would stop trusting the dashboard. Filters become one WHERE clause.
**Alternatives:** query the `complaints` table directly from each chart (simpler, but duplicated logic). **Trade-offs:** the view is nearly as large as the table (~70k rows) since the grain is fine; fast enough for this size.
**Interview:** "One shared definition means one version of the truth; a test proves the dashboard and the trend view agree."

**Decision:** The 3 insights are SQL comparisons (last 3 complete months vs the 3 before; busiest month vs median; monetary relief rate), not AI. They respect the filters and say so when there is not enough history.
**Reason:** Numbers must be exact and repeatable; an LLM could misread them. Writing the tests found a real bug (an issue present in only one period gave NaN and crashed).

**Decision:** Monthly trend charts leave out the partial latest month (Oct 2026, 14 days).
**Reason:** The first draft showed a sharp fake drop at the right edge, which would read as "complaints collapsed". Totals and KPIs still include all data.

**Decision:** On-time % stays as a KPI (shown to 3 decimals, 99.996%) with a note, and its chart axis starts at 98%.
**Reason:** At 2 decimals it rounded to "100.00%" although 3 complaints were late; the metric barely moves (see Phase 1).

**Decision:** Colour follows the entity: each product has one fixed colour from a colourblind-checked palette; single-series charts use one blue; the map uses a one-hue light-to-dark ramp.

**Finding (honest limit):** the map counts raw complaints, so big states look worst. Per-customer rates would need customer counts per state, which we do not have.

## Phase 5 — AI enrichment (build, before the first real run)
**Decision:** Use Google's free Gemini API tier instead of a paid provider (this supersedes the Phase 0 note about the Anthropic SDK).
**Reason:** The user does not want to spend money. A local model was ruled out by hardware (7.3 GB RAM, no GPU: only ~3B models fit, roughly 30-60 s per complaint and weaker accuracy). All LLM calls go through one wrapper (`src/ai/llm.py`), so the provider can change in one file.
**Alternatives:** Groq free tier (open Llama models), local Ollama, paid Claude Haiku. **Trade-offs:** free tiers have rate limits (calls are throttled and retried, runs resume where they stopped) and limits can change; masked public complaint text is sent to Google, acceptable for public data but not for real customer data.
**Interview:** "I isolated the model behind one function, so moving from a free tier to a private deployment at a bank is a one-file change."

**Decision:** Sample 1,501 complaints once (seed 42) and save the ids in `triage_sample`: narratives only, first copy of duplicated texts only, spread proportionally over products (credit card 594, checking/savings 372, credit reporting 311, debt collection 129, ...).
**Reason:** Reproducible, no template bias, and a fixed pool from which Phase 6 draws the 100 gold complaints. Small because of free-tier limits; the run resumes across days.

**Decision:** Presidio PII masking with the small spaCy model; locations and the company name are not masked; `{$...}` amounts are kept; custom rule for 8-17 digit account numbers.
**Reason:** Names, phones, e-mails, SSNs and account numbers must not leave the system; state/city and dollar amounts are useful for triage. Tested: phone, e-mail and account number are removed, amounts kept.
**Caveat:** a rule-based phone pattern also tags SSN-shaped text, which is fine because it is masked either way.

**Decision:** Pydantic schema with hard limits (severity 1-5, confidence 0-1, fixed category lists); one retry on invalid output, then the row is stored as `failed` and retried on the next run. Results are keyed by (complaint, prompt version) with model name, tokens and timestamp.
**Reason:** Traceability (which model and prompt gave which answer) and a fair v1-vs-v2 comparison in Phase 6.

**Decision:** The prompt shows the model the product and the consumer's chosen issue category as well as the narrative, and contains a severity rubric (highest level that applies), category definitions and 3 examples.
**Reason:** Analysts see those fields too. Phase 6's labeling page will show a human the same context so the comparison is fair.

**Decision:** `cost_usd` is an estimate of what the same run would cost on a paid plan (needs list prices in `.env`); the real bill is 0.
**Reason:** The guide asks for cost per complaint; token counts are always stored.

## Phase 5 — AI enrichment (results)
**Decision:** Use `gemini-3.5-flash-lite` for bulk triage. Probed your free key: `gemini-2.5-flash` and `-flash-lite` are closed to new users (404); `3.1-flash-lite`, `3.5-flash-lite`, `3.5-flash` and `3.8-flash` work.
**Reason:** Flash-Lite is fast (~1-2 s per call, no hidden "thinking" tokens) and cheap on paid plans; the 3.8 Flash model took 66 s for one trivial call.

**Result (200 complaints, prompt v1):** 100% valid structured output on the first or second try (target >= 98%). 1,319 input and 109 output tokens per complaint. No rate-limit errors at 15 requests/minute (about 4 s per complaint). Real bill on the free tier: $0. At the paid-tier list price ($0.30 / $2.50 per 1M tokens in/out, read from Google's pricing page) the same run costs about $0.00067 per complaint, well under the $0.01 target.
**Daily limit:** not reached after 200 requests; the true daily cap is still unknown (the runner stops cleanly and resumes if it is hit).

**Decision:** Process only 200 of the 1,501 sampled complaints with v1 for now; run the full sample after the prompt is improved (v2) in Phase 6.
**Reason:** Reading 20 outputs against the text showed v1 over-flags `vulnerable_consumer` (35% of the 200; anyone alleging fraud is flagged because my rubric lists "victim of fraud") and leans on `fraud_scam`. Running a known-flawed prompt on 1,501 complaints would waste free-tier calls, and v1 must stay unchanged as the baseline for a fair v1-vs-v2 comparison. These are hypotheses to confirm against your hand labels in Phase 6, not conclusions.
**Interview:** "I read a sample of outputs before scaling, found a likely rubric flaw, and held the bulk run until I could measure and fix it."

**Decision:** The run order is a fixed pseudo-random shuffle (`hash(complaint_id)`), not ID order.
**Reason:** My first version processed the lowest IDs (oldest complaints) first, so any partial run was a biased sample. Found while planning the limited free-tier runs.

**Cross-check against the Phase 3 amount rule:** of 72 narratives with a `{$..}` amount, the AI left the amount empty in 5; of 67 amounts the AI returned, 66 appeared in the narrative's amount list.

## Phase 6 — Evaluation (build)
**Decision:** The gold set is 100 complaints with fixed product quotas (credit card 30, checking/savings 25, credit reporting 20, debt collection 12, vehicle loan 8, money transfer 5), drawn from the saved triage sample (narratives only, first copy of duplicated texts, 60-4,000 characters), shuffled so the labeler does not work product by product.
**Reason:** A random sample would be about 40% credit card and would barely test small products; quotas give a readable accuracy per product. First-copy-only stops the 578-copy template from dominating (Phase 1 finding). The length limit means the human reads the same text the AI sees (no truncation).

**Decision:** The labeling page shows the human the same masked text and the same rubric (a test checks the rubric text equals the one in prompt v1) and hides the AI's answer; labels are saved after every click.
**Reason:** A fair comparison needs the same information and independent labels. Saving each click means a 2-3 hour task can be split over several sittings.

**Decision:** Prompt v1 was run on all 100 gold complaints before any labeling; v1 stays frozen as the baseline.

**Bugs found while testing the page:** (1) Streamlit read `{$92.00} ... {$35.00}` as maths and coloured the narrative red; the text is now shown as escaped plain text. (2) The file watcher printed hundreds of harmless torchvision warnings; turned off in `.streamlit/config.toml`.

**Decision (Phase 6):** Offer the labeling task as an Excel workbook (`data/gold_labeling.xlsx`) as well as the web page; an importer validates each row (allowed root causes, severity 1-5, Yes/No, no half-filled rows, ids untouched) and writes the same `evals/gold_labels.csv`.
**Reason:** The user preferred a spreadsheet. Dropdowns reject typos, a Rubric sheet carries the same definitions the AI got, and the importer is repeatable (re-import replaces by complaint id). The workbook holds the masked complaint texts, so it lives in the gitignored `data/` folder.
