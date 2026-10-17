# FDE Project Guide: Complaint Intelligence Platform for Capital One (Built on Real CFPB Data)

> **Goal:** Build a portfolio project that looks like real Forward Deployed Engineer work. You take a real company's messy real-world data, build an AI system its team could actually use, measure that it works, and explain it to business people.
> **Level:** Fresher-friendly. No Kubernetes, no Terraform, no distributed systems. Every tool here can be learned in under a day.
> **Built by:** Claude (Claude Code), with **you learning through a quiz at the end of every phase**.
> **Time:** ~2–3 weeks if Claude builds it and you do the quizzes and reviews.

---

## Table of Contents

1. [The Problem (in plain words)](#1-the-problem-in-plain-words)
2. [What You Will Build](#2-what-you-will-build)
3. [Why This Impresses FDE Recruiters](#3-why-this-impresses-fde-recruiters)
4. [Tech Stack (fresher-friendly)](#4-tech-stack-fresher-friendly)
5. [Architecture](#5-architecture)
6. [Repository Structure](#6-repository-structure)
7. [How Learning Works: Quiz After Every Phase](#7-how-learning-works-quiz-after-every-phase)
8. [Timeline](#8-timeline)
9. [Phase 0 — Setup & Domain Basics](#phase-0--setup--domain-basics)
10. [Phase 1 — Discovery: Understand the Customer](#phase-1--discovery-understand-the-customer)
11. [Phase 2 — Data Ingestion from the CFPB](#phase-2--data-ingestion-from-the-cfpb)
12. [Phase 3 — Cleaning, Modeling & Messy Internal Data](#phase-3--cleaning-modeling--messy-internal-data)
13. [Phase 4 — Analytics Dashboard (the first quick win)](#phase-4--analytics-dashboard-the-first-quick-win)
14. [Phase 5 — AI Enrichment: Classify Every Complaint](#phase-5--ai-enrichment-classify-every-complaint)
15. [Phase 6 — Evaluation: Prove the AI Works](#phase-6--evaluation-prove-the-ai-works)
16. [Phase 7 — Regulation Lookup (RAG) & Systemic Risk Alerts](#phase-7--regulation-lookup-rag--systemic-risk-alerts)
17. [Phase 8 — The Analyst App (human in the loop)](#phase-8--the-analyst-app-human-in-the-loop)
18. [Phase 9 — Ship It: Docker, CI, Deploy, Present](#phase-9--ship-it-docker-ci-deploy-present)
19. [Final Review Routine](#final-review-routine)
20. [Interview Pitch & Questions](#interview-pitch--questions)
21. [Reference Links](#reference-links)

---

## 1. The Problem (in plain words)

The **Consumer Financial Protection Bureau (CFPB)** is a US government agency. When a customer has a problem with a bank, for example a wrong charge on a credit card or a mistake on a credit report, they can file a complaint with the CFPB. The CFPB forwards it to the bank, the bank must respond, and the complaint is published in a **public database**. That database is updated regularly and holds millions of complaints, with fields such as:

- the company, product (credit card, checking account…), issue, state, and date
- the consumer's own written story (the "narrative"), when they agree to share it
- how the company responded, and whether it responded **on time**

Big banks like **Capital One** receive thousands of these complaints. Their **complaints and compliance teams** must:

1. **Read and triage** each complaint quickly. Which ones are serious? Which involve real money lost?
2. **Respond on time.** Late responses are visible to regulators and the public.
3. **Spot patterns early.** 300 complaints about the same autopay bug is a systemic problem, not 300 separate issues.
4. **Know which laws apply.** A billing dispute may fall under *Regulation Z*, an unauthorized transfer under *Regulation E*, a credit report error under the *FCRA*.

Regulators fine banks heavily when complaint handling fails, so this is a real, expensive problem that companies pay to solve.

> **Your role in this project:** you're a Forward Deployed Engineer "deployed" at Capital One's compliance team. You use only the public CFPB data about Capital One. This is a **portfolio project**: it's not affiliated with Capital One or the CFPB, and you should say so in your README.

---

## 2. What You Will Build

**"ComplaintIQ"**, a complaint intelligence platform with 5 features:

| # | Feature | What it does for the compliance team |
|---|---|---|
| 1 | **Data pipeline** | Pulls Capital One complaints from the CFPB automatically, without duplicates |
| 2 | **Analytics dashboard** | Trends by product, issue, and state; on-time response rate |
| 3 | **AI triage** | For each complaint: root cause, severity (1–5), money involved, vulnerable consumer?, summary |
| 4 | **Regulation lookup + risk alerts** | Suggests which regulation applies (with the exact section cited) and flags fast-growing complaint patterns |
| 5 | **Analyst app** | A prioritized queue; the analyst reviews the AI's work, edits a drafted response, and approves it. Every action is logged |

Plus the parts that make it look professional:
- an **evaluation** proving how accurate the AI is
- a **messy "internal bank data" simulator** to practice real-world data cleaning
- a **one-page executive memo** and a **demo video**

---

## 3. Why This Impresses FDE Recruiters

| FDE skill | Where you show it |
|---|---|
| Understanding a customer's problem | Phase 1 discovery doc |
| Working with messy real data | Phases 2–3 |
| SQL + Python data work | Phases 2–4 |
| Applied LLMs (structured output, RAG) | Phases 5, 7 |
| Measuring AI quality (evals) | Phase 6 |
| Building a usable tool for non-engineers | Phase 8 |
| Responsible AI (PII, human approval, audit log) | Phases 5, 8 |
| Shipping (Docker, CI, deploy) | Phase 9 |
| Explaining to business people | Phases 1, 9 (exec memo, demo) |

---

## 4. Tech Stack (fresher-friendly)

| Purpose | Tool | Why this one |
|---|---|---|
| Language | **Python 3.11+** | Most common for data and AI |
| Database | **DuckDB** | A database in a single file. No server, fast, plain SQL |
| Data handling | **pandas** | Standard Python data library |
| AI model | One LLM API (e.g. Claude: `claude-haiku-5-5` for cheap bulk work, `claude-sonnet-5-5` for harder reasoning) | Structured outputs, good at reading text |
| Validation | **Pydantic** | Checks that the AI's output has the right shape |
| PII removal | **Microsoft Presidio** | Finds and masks names, phone numbers, account numbers |
| Embeddings / search | **sentence-transformers** (`all-MiniLM-L6-v2`) + **ChromaDB** | Free, runs locally, simple API |
| Clustering | **scikit-learn** | For grouping similar complaints |
| App / dashboard | **Streamlit** | Build web apps in pure Python |
| Charts | **Plotly** | Interactive charts in Streamlit |
| Packaging | **Docker** | Runs anywhere |
| CI | **GitHub Actions** | Runs tests automatically |
| Deploy | **Streamlit Community Cloud** or **Render** | Free tiers, one-click deploy |

---

## 5. Architecture

```
  CFPB Complaint API / CSV ─┐
  eCFR (federal regulations)┼──► Ingestion scripts (Python) ──► DuckDB (raw tables)
  Fake internal CRM (CSV)  ─┘                                        │
                                                                     ▼
                                                     Cleaning + SQL models (clean tables)
                                                                     │
                          ┌──────────────────────────────────────────┼──────────────────────────┐
                          ▼                                          ▼                          ▼
              PII masking → LLM triage                  Embeddings → ChromaDB          Analytics SQL views
              (root cause, severity, $, summary)         (complaints + regulations)
                          │                                          │
                          └────────────────┬─────────────────────────┘
                                           ▼
                  Streamlit app: Dashboard | Triage Queue | Complaint Detail | Risk Alerts
                                           │
                          Human approves drafts → Audit log (DuckDB table)
```

---

## 6. Repository Structure

```
complaintiq/
├── README.md
├── CLAUDE.md                    # instructions Claude follows (quiz + logs)
├── requirements.txt
├── .env.example                 # API key names only — never real keys
├── Dockerfile
├── data/                        # gitignored: raw downloads + complaintiq.duckdb
├── src/
│   ├── ingest/
│   │   ├── cfpb.py              # pull complaints
│   │   ├── regulations.py       # pull Reg E / Reg Z / FCRA text
│   │   └── fake_crm.py          # generate messy internal bank data
│   ├── transform/
│   │   ├── clean.py
│   │   ├── models.sql           # clean tables + views
│   │   └── match.py             # link complaints ↔ internal customers
│   ├── ai/
│   │   ├── pii.py               # Presidio masking
│   │   ├── triage.py            # LLM structured extraction
│   │   ├── schema.py            # Pydantic models
│   │   ├── regulations_rag.py
│   │   └── clusters.py          # systemic risk detection
│   ├── app/
│   │   ├── Home.py              # Streamlit entry
│   │   └── pages/               # Dashboard, Queue, Detail, Alerts
│   └── audit.py
├── evals/
│   ├── gold_labels.csv          # 100 hand-checked complaints
│   └── run_eval.py
├── tests/
├── .github/workflows/ci.yml
└── docs/
    ├── discovery.md
    ├── decision-log.md          # every important choice + reason
    ├── learning-log.md          # quiz questions, your answers, model answers
    ├── evals.md
    ├── exec-memo.md
    └── data-quality-report.md
```

---

## 7. How Learning Works: Quiz After Every Phase

Claude builds the code, and **you learn by being quizzed** at the end of every phase. This guide gives **core questions with model answers** for each phase (below each phase). Claude also asks **project-specific questions** about the actual choices it made.

### Step 1: Put this in `CLAUDE.md` at the start of the project (Phase 0)

Claude Code reads `CLAUDE.md` automatically every session, so this happens without you asking:

```markdown
# ComplaintIQ — instructions for Claude

## The user is a fresher learning through this project
- Explain new concepts in simple language with a small example before using them.
- Prefer simple, readable code over clever code. Add short comments explaining *why*.

## After finishing EVERY phase in FDE-Project-Guide-CFPB-Complaint-Intelligence.md, do this before moving on:

### 1. Update the decision log
Append to `docs/decision-log.md` each important choice made in the phase:
Decision · Reason (with numbers if measured) · Alternatives considered · Trade-offs · How to explain it in an interview (1–2 simple sentences).

### 2. Quiz the user (interactive)
- Ask 5 questions, ONE AT A TIME, and wait for the user's answer before continuing:
  - 3 questions from the "Understanding Check" of that phase in the guide
  - 2 project-specific questions about the actual code/choices/numbers from this phase
- After each answer: say what was right, gently correct what was wrong or missing,
  then give the model answer in simple words.
- If the user says "skip" or "I don't know", explain the answer simply with an example.
- At the end, give a score (e.g. 4/5) and list any topic to revisit.

### 3. Save the quiz
Append to `docs/learning-log.md`: phase name, each question, the user's answer,
the model answer, and topics to revisit.

### 4. Then ask: "Ready for the next phase?" — and wait.
```

### Step 2: How each quiz will feel

> **Claude:** Phase 2 done ✅. Quiz time: question 1 of 5. Why do we "upsert" complaints instead of just inserting them?
> **You:** So we don't get duplicates?
> **Claude:** Correct! 👍 To add to that: the CFPB can also *update* a complaint later (e.g. the company's response changes), and an upsert updates the existing row instead of adding a copy. Model answer: …

### Step 3: Learning log
By the end, `docs/learning-log.md` is your **personal interview study guide**: every question, your answer, and the correct answer.

---

## 8. Timeline

| Phase | What | Time (Claude builds, you review + quiz) |
|---|---|---|
| 0 | Setup & domain basics | 1 day |
| 1 | Discovery | 0.5 day |
| 2 | Ingestion | 1 day |
| 3 | Cleaning + messy data | 1–2 days |
| 4 | Dashboard | 1 day |
| 5 | AI enrichment | 1–2 days |
| 6 | Evaluation | 1–2 days (labeling is on you) |
| 7 | RAG + risk alerts | 1–2 days |
| 8 | Analyst app | 1–2 days |
| 9 | Ship & present | 1–2 days |
| — | Final review | 1 day |

**Costs:** LLM usage stays around **$5–15** if you process a sample (e.g. 5,000 complaints) instead of all of them. Everything else is free.

---

## Phase 0 — Setup & Domain Basics

### Goal
A working environment, and enough domain knowledge to understand what you're building.

### Why it matters
FDEs talk to business users. If you know the words they use (triage, systemic issue, timely response, regulation), you sound credible.

### Steps
1. **Install:** Python 3.11+, Git, VS Code, Docker Desktop (needed in Phase 9).
2. **Create** a GitHub repo `complaintiq` and clone it locally.
3. **Create a virtual environment** and `requirements.txt` with: `duckdb pandas requests pydantic python-dotenv streamlit plotly scikit-learn sentence-transformers chromadb presidio-analyzer presidio-anonymizer faker pytest` plus your LLM provider's SDK.
4. **API key:** create an LLM API key and **set a monthly spending limit** in the provider's console. Put it in `.env` (gitignored). Commit `.env.example` with only the variable name.
5. **Create `CLAUDE.md`** with the quiz instructions from [Section 7](#7-how-learning-works-quiz-after-every-phase).
6. **Create** empty `docs/decision-log.md` and `docs/learning-log.md`.
7. **Read (about 1 hour):**
   - The CFPB Consumer Complaint Database page and its **field reference** (what each column means).
   - Browse Capital One complaints on the CFPB website. Look at 10 real narratives.
   - One-paragraph summaries of: **Regulation E** (electronic transfers), **Regulation Z** (credit cards and billing errors), **FCRA** (credit reports), **FDCPA / Regulation F** (debt collection).

### Deliverables
- Repo with `CLAUDE.md`, `requirements.txt`, `.env.example`, and the docs folder.

### Done when
- [ ] `python -c "import duckdb, streamlit, chromadb"` works.
- [ ] You can explain what the CFPB is in two sentences.

### 🧠 Understanding Check: Phase 0

<details><summary><b>Q1. What is the CFPB complaint database, and why is it useful for this project?</b></summary>

It's a public database of complaints consumers filed against financial companies, including the company's response and often the consumer's own story. It's useful because it's **real, large, messy, and about a specific company**, which is exactly what FDEs work with. It also has a real business problem attached: banks must handle these complaints well or face regulators.
</details>

<details><summary><b>Q2. Why do we keep the API key in a <code>.env</code> file and not in the code?</b></summary>

Code goes to GitHub, and anyone could steal a key pushed there and spend your money. `.env` stays on your machine (it's in `.gitignore`). We commit `.env.example` so others know *which* variables are needed, without the secret values.
</details>

<details><summary><b>Q3. What does "triage" mean in complaint handling?</b></summary>

Sorting incoming complaints by urgency and type so the most serious ones (money lost, vulnerable customers, legal risk) get handled first, the same way a hospital emergency room triages patients.
</details>

<details><summary><b>Q4. Name two regulations and what they cover.</b></summary>

**Regulation E:** electronic fund transfers, e.g. unauthorized debit card transactions and how a bank must investigate errors. **Regulation Z (Truth in Lending):** credit cards and loans, e.g. how billing errors must be handled. (Also: FCRA covers credit report accuracy; FDCPA/Reg F covers debt collectors' behavior.)
</details>

<details><summary><b>Q5. Why set a spending limit on the LLM API?</b></summary>

A bug, like an accidental loop or running on millions of rows instead of a sample, could make thousands of calls and cost a lot. A limit caps the damage. FDEs think about **cost control** because customers care about it.
</details>

---

## Phase 1 — Discovery: Understand the Customer

### Goal
Write a short document describing the problem, the users, and how success is measured, **before** any code.

### Why it matters
FDEs are hired to solve the *right* problem. A recruiter reading your discovery doc sees you think like a consultant, not just a coder.

### Steps
1. Claude pulls a **quick sample** of ~500 recent Capital One complaints and prints basic stats: top products, top issues, % with a narrative, % responded on time.
2. Write `docs/discovery.md` (1–2 pages):
   - **Customer:** Capital One's complaints and compliance team (fictional engagement on public data).
   - **Users (personas):**
     - *Complaint Analyst:* reads and triages ~50 complaints a day. Wants to know quickly what each one is about and how serious it is.
     - *Compliance Officer:* wants early warning of patterns that could become regulatory problems.
     - *Head of Customer Operations:* wants trends and numbers for leadership.
   - **Problems today** (assumed): manual reading, inconsistent tagging, patterns spotted late.
   - **Success metrics:**

     | Metric | Target |
     |---|---|
     | AI severity / root-cause accuracy | ≥ 80% agreement with human labels |
     | Time to triage one complaint | from ~5 min (manual) to < 1 min (with AI) |
     | Systemic issue detection | Flags a growing pattern within 1 week |
     | Cost | < $0.01 per complaint |
   - **Out of scope:** automatically sending responses (humans always approve), real customer account data.
   - **Risks:** narratives contain personal details; the AI can be wrong; regulations are complex.

### Deliverables
- `docs/discovery.md`

### Done when
- [ ] A non-technical person can read it and understand what you're building and why.

### 🧠 Understanding Check: Phase 1

<details><summary><b>Q1. Why write a discovery document before coding?</b></summary>

So you build what the customer actually needs. Coding first often means solving the wrong problem. The document also gives you agreed **success metrics**, so later you can prove the project worked.
</details>

<details><summary><b>Q2. What is a persona, and why do we have three different ones?</b></summary>

A persona is a short description of a type of user and what they need. Different users need different things: the analyst needs speed per complaint, the compliance officer needs pattern alerts, the operations head needs summary numbers. That's why the app has a queue, alerts, *and* a dashboard.
</details>

<details><summary><b>Q3. Why is "automatically sending responses" out of scope?</b></summary>

Responses to complaints have legal consequences. An AI mistake sent to a customer or regulator could cause real harm. So the AI **drafts** and a **human approves**. This is called *human-in-the-loop*, and banks expect it.
</details>

<details><summary><b>Q4. Why is "≥ 80% agreement with human labels" a good metric?</b></summary>

It's measurable and easy for business people to understand. It answers "how often does the AI agree with a trained human?" We measure it in Phase 6.
</details>

<details><summary><b>Q5. What would you ask the real customer in your first meeting?</b></summary>

Examples: How do you triage today, and how long does it take? What counts as "severe" for you? Which products cause the most regulatory worry? Who must approve responses? Can customer data be sent to an external AI service?
</details>

---

## Phase 2 — Data Ingestion from the CFPB

### Goal
Automatically download Capital One complaints into DuckDB, safely re-runnable, with no duplicates.

### Why it matters
Getting data out of a customer's systems reliably is a large part of FDE work. Recruiters look for **idempotent**, **incremental** pipelines.

### Steps
1. **Check the data source first.** CFPB offers:
   - a **search API** (JSON, filterable by company and date)
   - a **bulk CSV download** of the full database

   Claude should check which is currently reachable. If the API is down or slow, use the CSV. Record the choice in the decision log; adapting to unreliable sources is a real FDE skill.
2. **Filter** to Capital One. The company name in the data is written like `CAPITAL ONE FINANCIAL CORPORATION`, so check the exact spelling in the data. Start with the **last 24 months**.
3. **Load into DuckDB** table `raw_complaints`, keeping all original columns plus `ingested_at`.
4. **Idempotent load:** use `complaint_id` as the primary key and **upsert** (insert new, update changed). Running the script twice must not create duplicates.
5. **Incremental load:** store the latest `date_received` already loaded. Next time, fetch only newer complaints, plus a small overlap window (e.g. the last 7 days) to catch updates.
6. **Reliability:** retries with a pause between attempts on network errors, a timeout on every request, and clear log messages (`Fetched 1,240 complaints, 32 new, 5 updated`).
7. **Data check:** print counts per month and per product; make sure no month is suspiciously empty.

### Key CFPB fields you'll use
`complaint_id`, `date_received`, `product`, `sub_product`, `issue`, `sub_issue`, `consumer_complaint_narrative`, `company_response` (to consumer), `timely` (response on time? Yes/No), `state`, `zip_code`, `submitted_via`, `tags` (e.g. Older American, Servicemember), `consumer_consent_provided`.

### Deliverables
- `src/ingest/cfpb.py`, the `raw_complaints` table, and a short ingestion log in the README.

### Done when
- [ ] Running ingestion twice gives the same row count.
- [ ] You know how many Capital One complaints you have and what % have narratives.

### 🧠 Understanding Check: Phase 2

<details><summary><b>Q1. What does "idempotent" mean, and why does our pipeline need it?</b></summary>

Running it once or ten times gives the **same result**. Pipelines get re-run all the time (after crashes, by schedulers, by mistake). Without idempotency every re-run would add duplicate complaints and break all the counts.
</details>

<details><summary><b>Q2. What's the difference between a full load and an incremental load?</b></summary>

A **full load** downloads everything every time: simple, but slow and wasteful. An **incremental load** downloads only what's new since the last run: fast and efficient. We add a small overlap window because older complaints can be updated after we first saw them.
</details>

<details><summary><b>Q3. What is an "upsert"?</b></summary>

"Update or insert": if a row with that `complaint_id` exists, update it; if not, insert it. It prevents duplicates and keeps changed records current.
</details>

<details><summary><b>Q4. Why do we add retries and timeouts to API calls?</b></summary>

Networks fail and servers get slow. A **timeout** stops the script waiting forever. **Retries** (with a pause that grows each time) handle temporary failures automatically, so the pipeline doesn't crash at 2 a.m. because of a 1-second blip.
</details>

<details><summary><b>Q5. Why doesn't every complaint have a narrative?</b></summary>

Consumers must **consent** to publish their story, and the CFPB removes personal details first. So only some complaints have text. Our AI features work on those, and the dashboard uses all of them.
</details>

---

## Phase 3 — Cleaning, Modeling & Messy Internal Data

### Goal
Turn raw data into clean, well-organized tables, and practice the hardest real-world FDE task: **joining the customer's messy internal data** with outside data.

### Why it matters
Real customers never have clean data. Showing that you can clean data and match records across systems is one of the strongest signals in an FDE portfolio.

### Steps

**A. Clean the CFPB data (`src/transform/clean.py` + `models.sql`)**
1. Standardize text: trim spaces, consistent casing for product and issue names.
2. Convert dates to proper date types; add `year_month` and `week` columns.
3. Convert `timely` from "Yes/No" to true/false.
4. Fix ZIP codes: keep them as **text** (leading zeros like `02134` matter). Note: the CFPB partially masks some ZIPs (e.g. `021XX`).
5. Flag missing values and record the counts.
6. Create clean tables and views:
   - `complaints`: one clean row per complaint
   - `v_monthly_trends`: complaints per month per product
   - `v_timeliness`: on-time response % by product and month

**B. Simulate Capital One's messy internal CRM (`src/ingest/fake_crm.py`)**
Real FDEs must link outside complaints to the customer's own records. You don't have Capital One's database, so **generate a fake one with Faker** that is deliberately messy:
- ~5,000 fake customers with name, state, ZIP, product, and account open date
- **Mess added on purpose:**
  - duplicate customers with slightly different names ("Jon Smith" / "SMITH, JONATHAN")
  - ZIP codes saved as numbers (leading zero lost)
  - dates in 3 formats
  - some missing states
  - products named differently from the CFPB ("CC" instead of "Credit card")
- Plant ~300 "true matches": fake customers whose state, ZIP prefix, product, and timing align with real CFPB complaints, so you can measure matching accuracy.

**C. Match complaints to customers (`src/transform/match.py`)**
1. Clean the CRM data first: fix ZIPs, parse all date formats, map product names to CFPB names, remove duplicates.
2. Match using simple rules: same state + same 3-digit ZIP prefix + same product + account opened before the complaint date.
3. Give each match a **confidence score**, e.g. +1 for each matching field.
4. Measure it against the 300 planted true matches: **precision** (of the matches found, how many were right?) and **recall** (of the true matches, how many did we find?).

**D. Data quality report (`docs/data-quality-report.md`)**
Row counts, missing values, issues found and fixed, and matching precision/recall.

### Deliverables
- Clean tables and views, the fake CRM generator, the matcher, and the data quality report.

### Done when
- [ ] Clean tables have no duplicate `complaint_id`.
- [ ] Matching precision and recall are measured and written down.

### 🧠 Understanding Check: Phase 3

<details><summary><b>Q1. Why store ZIP codes as text instead of numbers?</b></summary>

Numbers drop leading zeros: `02134` becomes `2134`, which is wrong and breaks matching. ZIP codes are **identifiers**, not quantities. You never add or average them, so they should be text.
</details>

<details><summary><b>Q2. Why did we create a fake messy CRM instead of using clean data?</b></summary>

Real customer data is always messy (duplicates, formats, naming differences). We can't access Capital One's real data, so we simulate realistic mess to practice the cleaning and matching FDEs do daily. Planting known true matches also lets us **measure** how good our matching is.
</details>

<details><summary><b>Q3. Explain precision and recall with the matching example.</b></summary>

**Precision:** of all the matches our code made, what % were correct? (Low precision means many wrong matches.)
**Recall:** of all the true matches that exist, what % did our code find? (Low recall means we missed many.)
Example: we made 200 matches, 180 correct → precision 90%. There were 300 true matches → recall 180/300 = 60%.
</details>

<details><summary><b>Q4. What's the trade-off when making matching rules stricter?</b></summary>

Stricter rules (more fields must match) give **higher precision** (fewer wrong matches) but **lower recall** (more real matches missed). Looser rules do the opposite. The right balance depends on the cost of each mistake: for compliance, a wrong match (linking the wrong customer) is usually worse than a missed one.
</details>

<details><summary><b>Q5. What is a SQL view and why use one for trends?</b></summary>

A view is a **saved query** that behaves like a table. Defining `v_monthly_trends` once means the dashboard, reports, and tests all use the same logic, so numbers stay consistent everywhere.
</details>

---

## Phase 4 — Analytics Dashboard (the first quick win)

### Goal
A simple, useful Streamlit dashboard, built **before** the AI parts.

### Why it matters
FDEs deliver value early. A useful dashboard in week 1 builds customer trust while you work on the harder AI features.

### Steps
1. **Streamlit app** with a sidebar filter for date range, product, and state.
2. **KPI cards** at the top: total complaints, % with narrative, **on-time response %**, % closed with monetary relief.
3. **Charts (Plotly):**
   - complaints per month (line), split by product
   - top 10 issues (bar)
   - complaints by state (map)
   - on-time response % by month (line)
   - company response types (bar)
4. **"Insights" box:** 3 auto-generated plain-English observations, computed with simple SQL comparisons, not AI. For example: *"Credit card complaints rose 22% vs. last quarter, driven by 'Problem with a purchase shown on your statement'."*
5. Every number on screen comes from the SQL views in Phase 3.

### Deliverables
- `src/app/pages/1_Dashboard.py`, with a screenshot in the README.

### Done when
- [ ] Filters update all charts.
- [ ] You can state 3 real findings about Capital One complaints.

### 🧠 Understanding Check: Phase 4

<details><summary><b>Q1. Why build the dashboard before the AI features?</b></summary>

It delivers **value quickly** with low risk, shows the customer you understand their data, and builds trust. AI features take longer and are riskier. FDEs plan for early wins.
</details>

<details><summary><b>Q2. Why compute the "insights" with SQL instead of an LLM?</b></summary>

Numbers must be **exactly right and repeatable**. SQL comparisons are precise and free; an LLM could make up or misread a number. Use AI where it adds value (reading text), not where simple code is more reliable.
</details>

<details><summary><b>Q3. What is a KPI? Give two from this dashboard.</b></summary>

A Key Performance Indicator, an important number leadership tracks. Examples: **on-time response rate** and **total complaints per month**.
</details>

<details><summary><b>Q4. Why must all charts use the same SQL views?</b></summary>

If each chart calculated numbers its own way, they could disagree, and the customer would stop trusting the whole dashboard. One shared definition means one version of the truth.
</details>

<details><summary><b>Q5. A complaint count went up 30%. Is that always bad news?</b></summary>

Not necessarily. It could be more customers overall, a new product launch, or seasonality (e.g. after holidays). You'd compare against a baseline, look at the rate per customer if available, and check which issues drove the increase before raising an alarm.
</details>

---

## Phase 5 — AI Enrichment: Classify Every Complaint

### Goal
Use an LLM to read each complaint narrative and produce **structured, validated** triage information, with personal data removed first.

### Why it matters
This is the core "applied AI" skill: turning unstructured text into reliable structured data, safely and cheaply.

### Steps
1. **Sample:** pick ~3,000–5,000 complaints that have narratives. Don't process millions; that's a cost decision you document.
2. **PII masking (`src/ai/pii.py`):** the CFPB already masks most details (you'll see `XXXX`), but run **Presidio** anyway to catch names, phone numbers, emails, and account numbers. Banks always ask "what personal data goes to the AI?", so have a good answer.
3. **Define the output schema (`src/ai/schema.py`) with Pydantic:**
   ```python
   class Triage(BaseModel):
       summary: str                       # 1–2 sentences
       root_cause: Literal["billing_error", "unauthorized_transaction", "fees_interest",
                           "credit_reporting_error", "customer_service", "fraud_scam",
                           "account_access", "payment_processing", "debt_collection", "other"]
       severity: int                      # 1 (minor) – 5 (critical); rubric in the prompt
       monetary_harm_usd: float | None    # amount at stake, if stated
       vulnerable_consumer: bool          # e.g. elderly, servicemember, hardship mentioned
       requested_remedy: Literal["refund", "correction", "explanation", "close_account", "other"]
       confidence: float                  # 0–1
   ```
4. **Write the prompt** with:
   - a **severity rubric** that spells out each level, e.g. *5 = money lost + vulnerable consumer or legal threat; 1 = general dissatisfaction*
   - 3 short examples (few-shot)
   - an instruction to use only information in the complaint
5. **Call the LLM** with structured output (JSON matching the schema). Validate with Pydantic; if validation fails, retry once, then mark the row as `failed`.
6. **Save** results to the `complaint_triage` table with `model_name`, `prompt_version`, `processed_at`, and `cost_usd`.
7. **Cost control:** use the cheap model, run in batches, skip already-processed complaints (idempotent again!), and print the total cost.

### Deliverables
- The `complaint_triage` table, the prompt file `prompts/triage_v1.txt`, and a cost summary.

### Done when
- [ ] ≥ 98% of processed complaints have valid output.
- [ ] You know the cost per complaint.

### 🧠 Understanding Check: Phase 5

<details><summary><b>Q1. Why do we force the LLM to return a fixed JSON schema instead of free text?</b></summary>

Free text can't be filtered, counted, or charted reliably. A fixed schema (validated by Pydantic) gives clean columns: severity is always a number from 1 to 5, and root cause is always one of the allowed categories. That makes the AI's output usable in dashboards, queues, and evaluations.
</details>

<details><summary><b>Q2. Why remove PII before sending text to the LLM?</b></summary>

To protect customers' privacy and follow bank security rules: personal data should leave the bank's systems as little as possible. Even though CFPB pre-masks narratives, a real deployment would use internal data that isn't masked, so we build the habit and the code.
</details>

<details><summary><b>Q3. What is a "severity rubric" and why put it in the prompt?</b></summary>

A clear definition of what each severity level means. Without it, the model (and humans!) would use "severity 4" inconsistently. A rubric makes results **consistent and explainable**, and it's what we evaluate against in Phase 6.
</details>

<details><summary><b>Q4. Why store <code>model_name</code> and <code>prompt_version</code> with every result?</b></summary>

So we know exactly which model and prompt produced each answer. If we improve the prompt later, we can compare v1 vs. v2 results and explain any change. This is called **traceability**.
</details>

<details><summary><b>Q5. How did we keep costs low?</b></summary>

Used a cheap, fast model for bulk work; processed a sample instead of everything; skipped already-processed rows; kept prompts short; tracked cost per complaint. FDEs must be able to tell a customer what the system costs to run.
</details>

---

## Phase 6 — Evaluation: Prove the AI Works

### Goal
Measure how accurate the AI triage is, using complaints checked by a human (you).

### Why it matters
Anyone can call an LLM. **Proving it works with numbers** is what separates strong candidates. This phase is probably the most impressive part of the project to an interviewer.

### Steps
1. **Gold set:** Claude picks **100 complaints** across different products and builds a simple Streamlit labeling page. **You** label each one using the same rubric (root cause, severity, vulnerable consumer).
   - This is the one part Claude must **not** do for you. If the AI labels its own test, the test is meaningless.
   - It takes about 2–3 hours, and you'll understand the data deeply afterwards.
2. **Run the evaluation (`evals/run_eval.py`):**
   - **Root cause:** accuracy, plus precision and recall per category, and a **confusion matrix** (which categories get mixed up).
   - **Severity:** exact-match %, **within ±1 %**, and especially *"did it miss any severity-5 complaints?"*
   - **Vulnerable consumer:** precision and recall.
3. **Error analysis:** read the 15 worst mistakes and group them. For example: *"confuses fees_interest with billing_error"*, *"under-rates severity when the money amount is small but the customer is elderly"*.
4. **Improve once:** change the prompt (clearer category definitions, a better rubric, extra examples) and save it as `triage_v2`. Re-run and compare v1 vs. v2 in a table.
5. **Write `docs/evals.md`:** results, mistakes, the improvement, and whether it's *good enough for the customer* and why.
6. **Add the eval to CI** (Phase 9) on a 30-complaint subset, so prompt changes can't silently make things worse.

### Deliverables
- `evals/gold_labels.csv`, the eval script, `docs/evals.md` with the v1 → v2 table.

### Done when
- [ ] You can say: "Root cause accuracy is X%, severity is within ±1 Y% of the time, and here's what it still gets wrong."

### 🧠 Understanding Check: Phase 6

<details><summary><b>Q1. Why must a human create the gold labels, not the AI?</b></summary>

The gold set is the "answer key". If the AI wrote the answer key, we'd be checking the AI against itself, and it would look perfect even when wrong. Human labels give an independent truth.
</details>

<details><summary><b>Q2. What is a confusion matrix and what does it tell us?</b></summary>

A table showing, for each true category, what the AI predicted. The diagonal is correct; everything else is a mix-up. It tells us *which* categories get confused (e.g. fees vs. billing errors), so we know exactly what to fix in the prompt.
</details>

<details><summary><b>Q3. Why do we care especially about missed severity-5 complaints?</b></summary>

Mistakes don't all cost the same. Rating a minor complaint as 3 instead of 2 is harmless; missing a critical complaint (money lost, vulnerable customer) could mean real harm and regulatory trouble. For compliance, **recall on high-severity complaints** matters most.
</details>

<details><summary><b>Q4. Why use "within ±1" for severity, not just exact match?</b></summary>

Severity is a scale and humans disagree slightly too (a 3 vs. a 4 is a judgment call). "Within ±1" shows whether the AI is in the right range, while exact match is stricter. Reporting both gives an honest picture.
</details>

<details><summary><b>Q5. How did you know prompt v2 was actually better?</b></summary>

We ran **the same 100 gold complaints** through v1 and v2 and compared the metrics side by side. One change, same test set, measured difference. That's a fair experiment. We also checked that no category got worse.
</details>

---

## Phase 7 — Regulation Lookup (RAG) & Systemic Risk Alerts

### Goal
Two advanced features, kept simple:
1. **Regulation lookup:** for a complaint, suggest which regulation might apply, **quoting the exact section**.
2. **Systemic risk alerts:** automatically detect groups of similar complaints that are growing fast.

### Why it matters
RAG (Retrieval-Augmented Generation) is one of the most in-demand AI skills, and pattern detection is what compliance teams value most.

### Part A: Regulation RAG (`src/ai/regulations_rag.py`)
1. **Get the regulation text** from the **eCFR** (the official online Code of Federal Regulations) via its API or website. Use 4 parts of Title 12:
   - Part **1005** (Regulation E)
   - Part **1026** (Regulation Z; start with the billing-error and credit card sections, as it's large)
   - Part **1022** (FCRA / Regulation V)
   - Part **1006** (Regulation F, debt collection)
2. **Chunk** the text by section (e.g. `§ 1005.11 Procedures for resolving errors`). Keep the section number and title with each chunk.
3. **Embed** the chunks with `all-MiniLM-L6-v2` and store them in **ChromaDB**.
4. **For a complaint:** search with its summary + root cause, retrieve the top 5 sections, then ask the LLM: *"Which (if any) of these sections may be relevant? Quote the section number and explain in 2 sentences. If none apply, say so."*
5. **Guardrails:**
   - Code checks that every cited section number was among the retrieved sections. Invented citations are rejected.
   - Show a clear label: **"Suggestion for compliance review — not legal advice."**
6. **Quick check:** hand-check 20 complaints. Is the suggested regulation sensible? Record the % in `docs/evals.md`.

### Part B: Systemic risk alerts (`src/ai/clusters.py`)
1. **Embed** complaint summaries from Phase 5.
2. **Group similar complaints** with clustering (scikit-learn `KMeans` with ~20–30 clusters is simplest; `HDBSCAN` is a stretch option).
3. **Name each cluster** with the LLM by giving it 10 example summaries, e.g. *"Autopay charged twice after card replacement"*.
4. **Detect growth:** count complaints per cluster per month and flag a cluster when **this month ≥ 2× the average of the previous 3 months** and the count is ≥ 10 (to avoid noise).
5. **Alert card:** cluster name, growth %, number of complaints, top states, severity mix, 3 example complaints, and suggested regulations (from Part A).

### Deliverables
- The regulation search with citations, the clusters table, and the risk-alert logic.

### Done when
- [ ] No invented citations get through.
- [ ] At least one real growing pattern is found and explained in plain English.

### 🧠 Understanding Check: Phase 7

<details><summary><b>Q1. What is RAG, in simple words?</b></summary>

**R**etrieval-**A**ugmented **G**eneration: first **find** the relevant documents (here, regulation sections), then give them to the LLM so it answers **based on those documents**. It reduces made-up answers and lets us show sources.
</details>

<details><summary><b>Q2. What are embeddings?</b></summary>

Lists of numbers that represent the *meaning* of text. Texts with similar meanings get similar numbers, so "charged twice" and "duplicate payment" end up close together even though the words differ. We use them for searching regulations and for grouping complaints.
</details>

<details><summary><b>Q3. Why do we check that cited sections were actually retrieved?</b></summary>

LLMs sometimes invent plausible-looking citations. In compliance a fake legal citation is dangerous. Checking every citation against the retrieved list is a simple **guardrail** that blocks hallucinated sources.
</details>

<details><summary><b>Q4. Why require "≥ 2× growth AND at least 10 complaints" for an alert?</b></summary>

Growth alone is noisy: 1 → 3 complaints is 3× growth but means nothing. The minimum count stops tiny clusters from creating **false alarms**. Too many false alarms and people start ignoring alerts.
</details>

<details><summary><b>Q5. Why label the regulation output "not legal advice"?</b></summary>

The AI suggests possibly relevant rules to *help* a compliance expert. It doesn't replace their judgment. Clear labeling sets the right expectation and is part of using AI responsibly in regulated industries.
</details>

---

## Phase 8 — The Analyst App (human in the loop)

### Goal
Combine everything into one app that the complaint analyst would actually use every day.

### Why it matters
FDEs build tools **non-engineers use**. A clear workflow with human approval and an audit log shows you understand how enterprises (especially banks) adopt AI.

### Pages
1. **Dashboard** (Phase 4).
2. **Triage Queue:** complaints sorted by priority. Priority = severity, + vulnerable consumer, + money involved, + days until the response deadline. Filters: product, severity, status. Colored severity badges.
3. **Complaint Detail:**
   - original narrative (PII-masked) + AI summary + extracted fields + confidence
   - **"Why this priority?"**: a plain explanation of the scoring
   - similar past complaints (embedding search) and how they were resolved
   - suggested regulations with citations (Phase 7)
   - **AI-drafted response letter:** polite, factual, no promises the bank can't keep
   - the analyst can **correct** any AI field (severity, root cause), **edit** the draft, and click **Approve** or **Reject**
4. **Risk Alerts:** the cluster alert cards from Phase 7.

### Audit log (`src/audit.py`)
Every action is saved to an `audit_log` table: who, what, when, AI value before, human value after. For example: *"analyst_1 changed severity 3 → 5 on complaint 1234567 at 10:42"*.

Human corrections are useful in two ways:
- Regulators expect a record of who decided what.
- The corrections become **new labeled data** for improving the prompt.

### Simple login
A basic username selector or password (Streamlit secrets) with two roles: **analyst** (queue, edit) and **manager** (also sees the audit log and alerts). Keep it simple, and describe in the README how a real bank would use single sign-on (SSO) instead.

### Deliverables
- The full Streamlit app with 4 pages, the audit log, and roles.

### Done when
- [ ] An analyst can go from the queue → a complaint → correct the AI → approve the draft, and the audit log shows it.

### 🧠 Understanding Check: Phase 8

<details><summary><b>Q1. What does "human in the loop" mean here?</b></summary>

The AI suggests (classification, priority, draft letter), but a **human reviews and approves** before anything is final. The AI speeds people up; it doesn't make the final decision.
</details>

<details><summary><b>Q2. Why is an audit log important for a bank?</b></summary>

Regulators may ask "who decided this, when, and based on what?" The audit log answers that. It also shows how often humans correct the AI, which is a great measure of AI quality in real use.
</details>

<details><summary><b>Q3. How is the priority score calculated, and why show "Why this priority?"</b></summary>

It combines severity, vulnerable-consumer status, money involved, and how close the response deadline is. Showing the reason makes the system **explainable**: analysts trust and use tools they understand, and can spot when the scoring is wrong.
</details>

<details><summary><b>Q4. How can analyst corrections improve the system over time?</b></summary>

Each correction is a new human label. Collected over time, they show where the AI is weak, and they can be added to the eval set or used as prompt examples. This is called a **feedback loop**.
</details>

<details><summary><b>Q5. Why two roles (analyst and manager)?</b></summary>

People should only see and do what their job needs (the **principle of least privilege**). Managers review audit logs and alerts; analysts work the queue. Banks always ask about role-based access.
</details>

---

## Phase 9 — Ship It: Docker, CI, Deploy, Present

### Goal
Make the project easy to run, automatically tested, live online, and well explained.

### Steps
1. **Docker:** a `Dockerfile` so `docker build` + `docker run` starts the app anywhere.
2. **Tests (`tests/`):** a few simple pytest tests:
   - upsert creates no duplicates
   - ZIP cleaning keeps leading zeros
   - invalid AI output is rejected by the schema
   - invented citations are blocked
   - the priority score is ordered correctly
3. **CI (`.github/workflows/ci.yml`):** on every push, run the tests + the eval on a small cached sample. The run fails if accuracy drops by more than 5 points.
4. **Deploy:** Streamlit Community Cloud or Render. Ship a **small pre-processed DuckDB file** (e.g. 2,000 triaged complaints), so the live demo makes no expensive AI calls.
5. **README:**
   - the problem in 3 lines + a screenshot/GIF
   - the architecture diagram
   - a **results table**: AI accuracy, severity ±1, cost per complaint, matching precision/recall
   - how to run it, and links to all docs
   - limitations + "how this would work at a real bank" (SSO, private AI deployment, real CRM integration)
   - a disclaimer: public CFPB data, not affiliated with Capital One or the CFPB
6. **Executive memo (`docs/exec-memo.md`, 1 page)** for the Head of Customer Operations:
   - what we built (3 lines)
   - 3 key findings from Capital One's data (from the dashboard and alerts)
   - AI quality in plain words (*"agrees with a trained reviewer 85% of the time; never missed a critical complaint in testing"*)
   - estimated time saved: *"triage from ~5 min to ~1 min per complaint"*, measured by timing yourself on 20 complaints with and without the app
   - risks and next steps
7. **3-minute demo video:**
   1. the problem (20s)
   2. the dashboard insight (30s)
   3. the queue → complaint detail → correct → approve (60s)
   4. a risk alert (30s)
   5. eval results (30s)
   6. what's next (10s)

### Deliverables
- A live URL, the README, the exec memo, the video, and green CI.

### 🧠 Understanding Check: Phase 9

<details><summary><b>Q1. Why use Docker?</b></summary>

It packages the app with everything it needs (Python version, libraries), so it runs the same on any computer or server. No more "it works on my machine".
</details>

<details><summary><b>Q2. What does CI do in this project?</b></summary>

**Continuous Integration** automatically runs tests (and our small AI eval) on every code change. If something breaks, or the AI gets less accurate, we find out immediately instead of in front of the customer.
</details>

<details><summary><b>Q3. Why does the live demo use pre-processed data?</b></summary>

To avoid paying for AI calls every time someone opens the demo, to avoid exposing the API key, and to keep the demo fast and reliable.
</details>

<details><summary><b>Q4. Who is the executive memo for, and how is it different from the README?</b></summary>

The memo is for **business leaders**: findings, value, risks, in plain language without code. The README is for **engineers**: how it works and how to run it. FDEs must write both.
</details>

<details><summary><b>Q5. How would this change at a real bank?</b></summary>

- Login through the bank's single sign-on (SSO).
- The AI model hosted privately, or with strict data agreements.
- Real CRM and case management integration (e.g. Salesforce).
- Larger scale with a proper database such as Postgres and scheduled pipelines.
- Formal security and model-risk reviews before going live.
</details>

---

## Final Review Routine

Do this once after Phase 9 (about 3 hours) before applying:

1. **Read `docs/learning-log.md`** (all the quizzes). Re-study every "topic to revisit".
2. **Read `docs/decision-log.md`.** For the 10 most important decisions, explain *what, why, and the alternative* out loud.
3. **Run it yourself:** ingestion → triage a few complaints → open the app → approve one → check the audit log.
4. **Mock interview.** Ask Claude:
   *"Act as an FDE interviewer. Using my decision log, learning log, and evals, ask me 10 questions one at a time, mixing technical and customer-facing ones. Push back on weak answers and tell me what to revisit."*
5. **Practice the 60-second pitch** below until it sounds natural.

---

## Interview Pitch & Questions

### 60-second pitch
> "I built ComplaintIQ, a complaint intelligence platform for Capital One's compliance team using real public CFPB complaint data. It ingests complaints with an idempotent pipeline, cleans them and matches them to a deliberately messy simulated CRM, and uses an LLM with PII masking and a validated schema to triage each complaint by root cause, severity, and money at stake. I measured it against 100 complaints I labeled myself: root cause accuracy went from X% to Y% after one prompt iteration. It also suggests relevant regulations with verified citations, flags fast-growing complaint patterns, and gives analysts a queue where they approve AI drafts, with every action audit-logged. I summarized the findings in a one-page executive memo."

### Be ready for
- Walk me through your data pipeline. What happens if it crashes halfway?
- How do you know your AI is accurate? What does it get wrong?
- How did you stop the model from inventing regulations?
- How would you handle customer data privacy at a real bank?
- What does it cost to run per complaint? How would you reduce it?
- The compliance team says "the severity scores feel wrong". What do you do? *(Get examples → compare to the rubric → check the eval → adjust the prompt/rubric with them → re-measure.)*
- What would you build next with 2 more weeks?

---

## Reference Links

- CFPB Consumer Complaint Database: https://www.consumerfinance.gov/data-research/consumer-complaints/
- CFPB complaint API documentation: https://cfpb.github.io/api/ccdb/
- eCFR (Code of Federal Regulations): https://www.ecfr.gov — Title 12, Parts 1005, 1006, 1022, 1026
- DuckDB: https://duckdb.org/docs/
- Streamlit: https://docs.streamlit.io
- Pydantic: https://docs.pydantic.dev
- Microsoft Presidio: https://microsoft.github.io/presidio/
- sentence-transformers: https://www.sbert.net
- ChromaDB: https://docs.trychroma.com
- scikit-learn clustering: https://scikit-learn.org/stable/modules/clustering.html

> **Note:** check that the CFPB API and download links work before Phase 2. Government data services sometimes change or go offline. If they do, use the bulk CSV or a public mirror (e.g. data.gov) and record that choice in the decision log.

---

*Build it with Claude, understand it through the quizzes, explain it like an FDE.*
