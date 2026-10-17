# Discovery: ComplaintIQ for Capital One's Complaints & Compliance Team

> Fictional engagement on public CFPB data. Not affiliated with Capital One or the CFPB.

## 1. The customer and the problem
Capital One's complaints and compliance team receives thousands of CFPB complaints. Each must be read, judged for seriousness, answered on time, and linked to the rules that apply. Missed patterns (e.g. one bug causing hundreds of complaints) become regulatory problems.

**Problems today (assumed):** manual reading, inconsistent tagging between analysts, patterns spotted late.

## 2. Users (personas)
| Persona | Needs |
|---|---|
| **Complaint Analyst** (~50 complaints/day) | Know fast what each complaint is about and how serious it is; a drafted response to review |
| **Compliance Officer** | Early warning of growing patterns; which regulation may apply |
| **Head of Customer Operations** | Trends and numbers for leadership |

## 3. What the data looks like (sample facts)
Source: CFPB Consumer Complaint Database, Capital One only (`CAPITAL ONE FINANCIAL CORPORATION`), Aug 2024 – Aug 2026.

| Fact | Value |
|---|---|
| Complaints (24 months) | **66,963** (one row per complaint, no duplicate IDs) |
| Per month | ~1,800 in 2024; ~2,300–3,000 in 2025–26 (January 2025 spike: 7,601) |
| Top products | Credit card 33.5%, Credit reporting 33.3%, Checking/savings 17.5%, Debt collection 10.7%, Vehicle loan 3.3% |
| Top issues | Incorrect info on report (13,036), Managing an account (8,748), Improper use of report (6,933), Purchase problem on statement (5,819) |
| With a consumer narrative | **39.1% (26,157)** |
| Company responded on time | **99.995%** (only 3 late of 66,963) |
| Response type | 82% closed with explanation, 12% non-monetary relief, 4.4% monetary relief |
| Tags | Servicemember 4,203; Older American 2,493 (+531 both) |
| Narrative length | median ~730 characters; 72% contain CFPB `XXXX` masking |

**Latest 500 complaints (26–31 Aug 2026):** credit card 43%, credit reporting 27%, checking/savings 16%; top issues incorrect information on report (93) and purchase problems (75).

### Important findings that change the plan
1. **The CFPB stopped publishing narratives** (announced 14 Aug 2026). The live API and bulk CSV have no narrative column. The narrative rate falls month by month (≈50% in 2025 → 12% in July 2026 → 0% in August 2026). Narratives for earlier complaints remain in the official **FOIA Reading Room "Narratives Archive"**, which is our narrative source.
2. **"On-time response %" is ~100%**, so as a KPI it barely moves. The dashboard still reports it but leads with volume, relief rates and issue trends. The priority score in Phase 8 uses "days until deadline" only as a minor input.
3. **January 2025 spike (7,601 complaints, 4,474 "Managing an account" on checking/savings)** is a real systemic event our risk-alert logic (Phase 7) should be able to catch.
4. Because narratives exist only up to mid-2026 and thin out after 2025, AI triage uses complaints that have a narrative (26k available, we process ~3–5k sample).

## 4. Success metrics
| Metric | Target |
|---|---|
| AI severity / root-cause accuracy | ≥ 80% agreement with human labels |
| Time to triage one complaint | from ~5 min (manual) to < 1 min (with AI) |
| Systemic issue detection | Flags a growing pattern within 1 week |
| Cost | < $0.01 per complaint |

## 5. Out of scope
- Automatically sending responses (humans always approve).
- Real customer account data (we use a simulated CRM).
- Complaints without narratives get no AI triage; they appear in analytics only.

## 6. Risks
- Narratives contain personal details → PII masking before any LLM call.
- The AI can be wrong → human review, evaluation against hand labels.
- Regulations are complex → suggestions are cited and labeled "not legal advice".
- Data source risk: the CFPB changed what it publishes mid-project; the pipeline must tolerate a missing narrative column.

## 7. Questions for the real customer (first meeting)
How do you triage today and how long does it take? What counts as "severe"? Which products worry regulators most? Who must approve responses? Can complaint text be sent to an external AI service?
