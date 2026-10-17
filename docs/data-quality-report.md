# Data Quality Report (Phase 3)

Reproduce: `python -m src.transform.clean`, `python -m src.ingest.fake_crm`, `python -m src.transform.match`.

## 1. CFPB complaints: raw → clean
| Item | Result |
|---|---|
| `raw_complaints` rows | 70,576 (2024-08 → 2026-10) |
| `complaints` rows | 70,576, **no duplicate `complaint_id`** (checked on every build; also covered by `tests/test_models.py`) |
| Views | `v_monthly_trends` (257 rows), `v_timeliness` (257 rows) |

**Missing values in the clean table**
| Column | Missing | % | Meaning |
|---|---|---|---|
| narrative | 44,419 | 62.9% | no consent / not web / CFPB stopped publishing narratives |
| zip5 | 8,850 | 12.5% | ZIP masked by the CFPB (`604XX`), fully masked, or blank |
| sub_product | 3,330 | 4.7% | blank, plus "I do not know" turned into NULL |
| sub_issue | 1,224 | 1.7% | blank |
| zip3 | 757 | 1.1% | ZIP missing or masked before the 3rd digit (usable prefix lost) |
| state | 217 | 0.3% | blank |

**Issues found and fixed**
- Text trimmed and repeated spaces collapsed (product/issue casing was already consistent, nothing to change).
- Dates cast to DATE; added `year_month` and `week`. No unparseable or out-of-order dates.
- `timely` → boolean. `tags` → `is_older_american` (3,263), `is_servicemember` (5,003; includes complaints tagged with both).
- ZIP kept as TEXT in three forms: `zip5` (full), `zip3` (prefix, also for masked ZIPs), `zip_masked` flag (8,745 masked).
- "I do not know" sub-product → NULL; narrative whitespace/line breaks collapsed; `has_narrative` = 26,157.
- Added response helpers: `is_final_response` (796 "In progress" are not final), `got_monetary_relief` (3,199), `got_any_relief`.
- Added for the AI phases: `narrative_chars`, `amounts_usd` (dollar amounts found in `{$...}` form; 8,238 narratives), `narrative_copies` and `is_first_copy`. **25,078 narratives are unique (first copy); 1,224 complaints share their text with another one (largest template: 578 copies).** AI sampling and the gold set use `is_first_copy` only.
- Added `missing_from_bulk`: the 55 complaints (all "In progress", Jul-Aug 2026) that the newest bulk file no longer lists are flagged instead of silently kept.
- Dropped from the clean table: `company` and `company_public_response` (constant / 100% empty).

## 2. Fake messy CRM
Generated with Faker (seed 42): **5,100 records for 4,700 people**, 400 duplicate records, 300 people planted as true matches of real complaints (240 with a full public ZIP, 60 with a masked ZIP). Planted customers opened the account 30–540 days before the complaint (a simulation assumption).

| Mess added | Count in `crm_raw` |
|---|---|
| Duplicate records with different name style | 400 |
| ZIP saved as a number (leading zero lost) or ZIP+4 | 393 are shorter than 5 digits; ~5% ZIP+4 |
| Dates in 3 formats | all rows |
| Missing state | 259 (≈5%) |
| Product spelled differently ("CC", "DDA", "VEH LOAN"…) | all rows |

**CRM cleaning results:** all ZIPs and dates parsed (0 failures), all products mapped (0 unmapped), **224 missing states filled from the ZIP prefix** (35 remain missing), and duplicates merged: **5,100 records → 4,700 customers, exactly the true number of people**.

## 3. Matching complaints ↔ customers
Rule: state + 3-digit ZIP + product must agree and the account must be opened before the complaint. Score = 4 for those, +2 for an exact 5-digit ZIP, +2 for an account opened within 18 months before the complaint (max 8). Measured against the 300 planted pairs.

| Rule set | Matches made | Correct | Precision | Recall |
|---|---|---|---|---|
| Loose: best customer per complaint, any score | 22,215 | 292 | 1.3% | 97.3% |
| One customer ↔ one complaint, ties excluded, score ≥ 4 | 231 | 92 | 39.8% | 30.7% |
| Same, score ≥ 8 (strict) | 104 | 87 | **83.7%** | 29.0% |

A further 594 links were **ambiguous** (tied scores) and are kept in `complaint_matches` with `ambiguous = true` for human review; 46 of them were in fact right.

**Reading the numbers**
- The CFPB data has no customer name or account number, so state + ZIP + product + timing is weak evidence. Loose rules find nearly everything but bury it in wrong links; strict rules are mostly right but miss most true pairs. For compliance, a wrong link (wrong customer) is worse than a missed one, so the strict, reviewable setting (precision ≈ 84%) is the one to use, with ambiguous links reviewed by a person.
- Precision and recall are properties of this *simulation* (how many background customers happen to share a ZIP, how the plants were timed), not predictions of real-bank accuracy. A real deployment would match on a customer or account ID.
- A recall improvement would need another signal (e.g. a masked account fragment in the narrative) rather than looser rules.
