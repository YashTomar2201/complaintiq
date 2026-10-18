# Learning Log

Quiz questions, your answers, model answers, and topics to revisit — one section per phase.

## Phase 0 — Setup & Domain Basics (score: 3.5/5)

**Q1. What is the CFPB complaint database and why is it useful here?**
Your answer: a collection of financial complaints. (Partial)
Model answer: Public database of consumer complaints against financial companies, incl. the company's response and often the consumer's story. Useful because it's real, large, messy and about one company, with a real business problem (regulators).

**Q2. Why keep the API key in `.env`, not code?**
Your answer: so people on GitHub can't see and misuse it. (Correct)
Model answer: Code goes to GitHub; leaked keys get abused. `.env` is gitignored; `.env.example` lists variable names only.

**Q3. What is triage?**
Your answer: giving priority to urgent complaints. (Correct)
Model answer: Sorting by urgency/type so serious ones (money lost, vulnerable customers, legal risk) are handled first, like an ER.

**Q4. Why a venv with Python 3.11 instead of upgrading global Python?**
Your answer: 3.10 is standard, project needs 3.11, so we upgraded the venv. (Partial)
Model answer: Isolation. 3.10 is just the global default, and the venv was created with 3.11, not upgraded. Project gets its own Python/libraries without affecting anything else; reproducible via requirements.txt.

**Q5. Why cheap model for bulk and stronger model for hard reasoning?**
Your answer: to reduce token usage and cost. (Mostly correct)
Model answer: Cost control. Bulk triage is simple and high-volume, so the cheap fast model is enough; the costlier model is used only where reasoning adds value. (Note: the split reduces cost per token, not the number of tokens.)

**Revisit:** what the CFPB database contains (response, timeliness, narrative with consent); purpose of virtual environments.

## Phase 1 — Discovery (score: 3.5/5)

**Q1. Why write a discovery document before coding?**
Your answer: to get insights from the dataset and learn how to clean it. (Partial)
Model answer: To build what the customer actually needs: users, problem, scope and agreed success metrics, so we can prove the project worked. Data exploration/cleaning plans belong in the data profile, a separate document.

**Q2. What is a persona and why three?**
Your answer: a person who looks after customer needs; different personas for different needs, forming a hierarchy. (Partial)
Model answer: A persona is a short description of a type of user and what they need, not a team member, and not a hierarchy. Analyst = speed per complaint, Compliance Officer = pattern alerts, Operations Head = summary numbers; hence queue, alerts, dashboard.

**Q3. Why is "automatically sending responses" out of scope?**
Your answer: the AI might miss a factor and make a mistake, making the customer angrier. (Correct)
Model answer: Replies have legal consequences; AI drafts, a human approves (human-in-the-loop).

**Q4. What to do with the ~100% on-time metric (project-specific)?**
Your answer: show it less prominently and let other figures stand out. (Correct)
Model answer: A near-constant number gives no insight, so lead with metrics that vary; keep it as a small KPI because a drop would matter.

**Q5. Why keep templated duplicate narratives in analytics but dedupe for AI sample/gold set? (project-specific)**
Your answer: analytics needs frequencies; for the AI we use each complaint once so it learns how to respond. (Partly correct)
Model answer: Analytics must count every complaint. For the AI sample and gold set, 576 copies of one text would dominate the accuracy score (it would mostly measure one complaint type), waste LLM cost and your labeling time. We are not training the AI; we are building a fair, varied test.

**Revisit:** purpose of discovery vs data profiling; what a persona is; evaluation sampling bias.

## Phase 2 — Ingestion (score: 3/5)

**Q1. What does "idempotent" mean and why does the pipeline need it?**
Your answer: same result for same input; needed so we give the same answer for the same question. (Mostly)
Model answer: Running the load once or ten times gives the same result. Pipelines are re-run after crashes, by schedulers, by mistake; without idempotency re-runs add duplicates and break counts. (Ours: archive re-run = 0 new, 0 updated.)

**Q2. Full vs incremental load; why a 7-day overlap?**
Your answer: I don't know.
Model answer: Full = download everything each time (simple, slow). Incremental = only what's new since last run (fast). Overlap re-fetches recent days because complaints change after first seen (e.g. "In progress" later closed); the upsert applies the changes. We saw 610 such changes.

**Q3. What is an upsert?**
Your answer: update if present, insert if absent. (Correct)
Model answer: Update-or-insert on `complaint_id`; prevents duplicates and keeps rows current; ours also never lets a NULL narrative overwrite an existing one.

**Q4. Why was filtering raw lines safe for the bulk file but not for the archive? (project-specific)**
Your answer: bulk has no narratives, so no line breaks; archive has narratives. (Partly; "filter out" wording wrong, we keep Capital One lines)
Model answer: Bulk: one complaint = one line, so a line filter keeps whole rows. Archive: narratives contain line breaks, so one complaint spans many lines; the company column comes after the narrative, so only the last fragment would match and earlier fragments (ID, date, text) would be dropped, giving broken rows. Use a real CSV parser there.

**Q5. Why can a NULL narrative never overwrite an existing one? (project-specific)**
Your answer: it would erase the history of the complaint. (Mostly)
Model answer: Bulk/API have no narrative column, so "empty" means "this source doesn't carry text", not "text deleted". The archive is the only source of narratives (CFPB stopped publishing them); overwriting would destroy the text the AI phases need and it could not be recovered by re-running the API.

**Revisit:** full vs incremental loads and why overlap exists; CSV rows spanning multiple lines.

## Phase 3 — Cleaning, Modeling & Messy Data (score: 2/5)

**Q1. Why store ZIP codes as text, not numbers?**
Your answer: I don't know.
Model answer: Numbers drop leading zeros (02134 -> 2134), which is wrong and breaks matching (393 CRM records lost their zero). ZIPs are identifiers, not quantities: never added or averaged, so text.

**Q2. Why a fake messy CRM, and why plant 300 known matches?**
Your answer: I don't know.
Model answer: We cannot access Capital One's real data and real data is always messy (duplicates, formats, naming), so we simulate it to practice cleaning/matching. Planted matches are an answer key so matching quality can be measured instead of guessed.

**Q3. Explain precision and recall with the matching example.**
Your answer: I don't know.
Model answer: Precision = of matches made, % correct (180/200 = 90%). Recall = of true matches, % found (180/300 = 60%). Ours: strict 87/104 = 83.7% precision, 87/300 = 29% recall.

**Q4. Loose (97% recall, 1.3% precision) vs strict (84% precision, 29% recall): which for compliance? (project-specific)**
Your answer: linking a complaint to the wrong customer costs more, so strict is better. (Correct)
Model answer: Stricter rules raise precision and lower recall. A wrong link is worse than a missed link for compliance; ties go to human review.

**Q5. Why keep the answer key away from the matching code? (project-specific)**
Your answer: so there is no cheating causing 100% precision and recall. (Correct)
Model answer: If the matcher could see the answers, the measurement would be meaningless. The same principle applies to the human-labelled gold set in Phase 6.

**Revisit:** ZIP/identifier types; why we simulate messy data; precision vs recall (use the 200/180/300 example); SQL views (guide Q5 not asked: a view is a saved query so dashboard, reports and tests share one definition).

## Phase 4 — Analytics Dashboard (score: 3.25/5)

**Q1. Why build the dashboard before the AI features?**
Your answer: to have a showable project. (Partial)
Model answer: Delivers value quickly with low risk, shows the customer we understand their data, builds trust while the slower, riskier AI features are built. FDEs plan early wins.

**Q2. Why compute the insights with SQL, not an LLM?**
Your answer: AI might make mistakes or hallucinate; SQL gives accurate data. (Correct)
Model answer: Numbers must be exact and repeatable; use AI where it adds value (reading text), plain code where it is more reliable.

**Q3. What is a KPI? Two examples.**
Your answer: key performance indicator giving valuable insights; total complaints and with a narrative. (Mostly)
Model answer: An important number leadership tracks to see how things are going. Better examples here: on-time response rate, closed with monetary relief. "With a narrative" is a data-completeness stat.

**Q4. Why did the monthly charts drop sharply at the right edge, and what did we do? (project-specific)**
Your answer: there was a spike in January. (Incorrect)
Model answer: The latest month (October 2026) is partial (data ends 14 Oct), so it has about half the complaints and looks like a collapse. We left the partial month out of the monthly trend charts; totals and KPIs still include everything. The January 2025 spike is a separate, real event.

**Q5. Is a 16% rise in credit card complaints always bad news? (project-specific)**
Your answer: not necessarily; more people may have bought the cards. (Correct)
Model answer: Could be more customers, a launch or seasonality. Compare to a baseline, look at the rate per customer if available, and check which issue drove it (here: purchase problems on the statement, +152) before raising an alarm.

**Revisit:** partial periods in time series; what makes a good KPI; why early wins matter.

## Phase 5 — AI Enrichment (score: 4/5)

**Q1. Why force the LLM to return a fixed JSON schema?**
Your answer: so it can be processed and read by machine easily. (Correct)
Model answer: Free text can't be filtered, counted or charted; a validated schema gives clean columns (severity always 1-5, root cause from a fixed list) usable in dashboards, queues and evaluation.

**Q2. Why remove PII before sending text to the LLM?**
Your answer: to prevent leaking sensitive info. (Correct)
Model answer: Personal data should leave the bank's systems as little as possible. CFPB masking is not complete and real internal text is unmasked, so we build the habit; we tested phone/email/account numbers are removed while dollar amounts are kept.

**Q3. What is a severity rubric and why in the prompt?**
Your answer: I don't know.
Model answer: Written definitions of each severity level (5 = money lost + vulnerable/legal threat ... 1 = general dissatisfaction). Without it the model and humans would use "4" inconsistently; it makes results consistent, explainable, and is the standard Phase 6 measures against.

**Q4. Why store model name and prompt version with every result? (project-specific)**
Your answer: to see which models perform best with what prompt; helps improve prompts. (Correct)
Model answer: Traceability: know exactly what produced each answer; compare v1 vs v2 on the same complaints; table is keyed on (complaint, prompt version) so v1 stays when v2 runs.

**Q5. Why triage only 200 of 1,501 and stop? (project-specific)**
Your answer: to check accuracy first; improve the prompt, then test on a larger set. (Correct)
Model answer: Reading outputs showed a likely flaw (35% flagged vulnerable); running it on all 1,501 would waste free-tier calls, and v1 must stay unchanged as the baseline for a fair v1-vs-v2 comparison.

**Revisit:** what a rubric is and why consistency matters.

## Phase 6 — Evaluation (score: 3/5)

**Q1. Why must a human create the gold labels, not the AI?**
Your answer: so the AI can test its labels against actual truth. (Mostly)
Model answer: The gold set is the answer key. If the AI wrote it, we would check the AI against itself and it would look perfect even when wrong. Human labels are an independent truth. (Same reason Gemini Pro should not fill the sheet.)

**Q2. What is a confusion matrix and what did v1's tell us?**
Your answer: I don't know.
Model answer: A table of true category (rows) vs AI prediction (columns); the diagonal is correct, off-diagonal cells are mix-ups. v1 confused debt collection and fraud with credit reporting (3 + 2 cases) and used customer service where the human picked the underlying problem. That drove the v2 tie-breaker rules.

**Q3. Why do missed severity-5 complaints matter most?**
Your answer: they carry the most importance; accuracy on them shows the pipeline handles sensitive cases. (Correct)
Model answer: Errors have unequal costs. Missing a critical complaint (money lost, vulnerable consumer) risks real harm and regulatory trouble; high-severity recall matters most. v1 missed 3 of 14, v2 missed 0.

**Q4. Why might v2's improvement be smaller than it looks? (project-specific)**
Your answer: some categories performed worse than before. (Correct)
Model answer: Also: small sample (11 fixed vs 7 broken = net +4) and v2 was written after studying errors in the same 100 complaints (optimistic). Regressions: fees_interest recall 0.73 to 0.64, vulnerable false alarms 4 to 8.

**Q5. What does it teach us that my guess about "vulnerable" was wrong? (project-specific)**
Your answer: AI is not always 100 percent correct. (Missed the point)
Model answer: The wrong one was the human reviewer's guess. Reading a handful of outputs gives impressions (small, non-random, confirmation bias). Hypotheses must be checked against independent labels on a proper sample: the real v1 problems were low severity and category confusion, not "vulnerable".

**Revisit:** confusion matrix; evaluating with numbers not impressions; why holdout data matters.
