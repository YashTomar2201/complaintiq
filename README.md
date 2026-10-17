# ComplaintIQ

A complaint intelligence platform built on **public CFPB complaint data about Capital One**: ingestion, cleaning, analytics, AI triage, regulation lookup, risk alerts and a human-in-the-loop analyst app.

> **Disclaimer:** portfolio project using public CFPB data. Not affiliated with Capital One or the CFPB.

## Setup
```
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # then add your API key
```

_Full README (results, architecture, screenshots) is completed in Phase 9._

## Ingestion (Phase 2)
```
python -m src.ingest.cfpb archive   # narratives archive (FOIA Reading Room zips in data/archive/)
python -m src.ingest.cfpb bulk      # bulk CSV: refreshes status, adds newest rows (add --download to re-fetch)
python -m src.ingest.cfpb api       # incremental from the live API (last loaded date - 7 days)
python -m src.ingest.cfpb check     # counts per month/product, flags empty months
```
Log of the first run (all loads are upserts keyed on `complaint_id`; re-runs add nothing):
```
archive: fetched 66,963, 66,963 new, 0 updated | table rows 0 -> 66,963
archive (again): 0 new, 0 updated                 | table rows 66,963
bulk:    fetched 70,521, 3,613 new, 610 updated   | table rows 66,963 -> 70,576
bulk (again): 0 new, 0 updated                    | table rows 70,576
api:     fetched 53, 0 new, 0 updated             | table rows 70,576
check:   70,576 rows | 26,157 with narrative (37.1%) | months 2024-08..2026-10, none missing or low
```
Why three sources: the CFPB stopped publishing narratives in Aug 2026, so text comes from the archive while structure/status comes from the bulk file and API. Details in `docs/data-profile.md`.
