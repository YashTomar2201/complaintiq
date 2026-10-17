"""CFPB ingestion into DuckDB (table raw_complaints).

Three sources, because no single one is complete (see docs/data-profile.md):
  archive : FOIA narratives archive (has narrative text, but status can be stale)
  bulk    : official bulk CSV (no narratives, fresher status + newest rows)
  api     : live search API (no narratives), used for small incremental loads

Every load is an UPSERT keyed on complaint_id, so re-running never duplicates rows.

Usage (from project root):
  python -m src.ingest.cfpb archive | bulk | api | check
  python -m src.ingest.cfpb bulk --download     # re-download the bulk zip first
"""
import glob
import io
import logging
import sys
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "complaintiq.duckdb"
ARCHIVE_GLOB = str(ROOT / "data" / "archive" / "*.zip")
BULK_ZIP = ROOT / "data" / "complaints.csv.zip"
BULK_URL = "https://files.consumerfinance.gov/ccdb/complaints.csv.zip"
API_URL = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"

COMPANY_FILTER = "CAPITAL ONE FINANCIAL CORPORATION"  # exact spelling used in the data
START_DATE = "2024-08-01"  # "last 24 months": matches the start of the narratives archive
OVERLAP_DAYS = 7  # re-fetch the last week on incremental loads to catch updated complaints
API_PAGE = 1000
API_MAX_WINDOW = 10_000  # the API cannot page beyond this many results

log = logging.getLogger("cfpb")

# CSV header -> our snake_case column name
RENAME = {
    "Date received": "date_received", "Product": "product", "Sub-product": "sub_product",
    "Issue": "issue", "Sub-issue": "sub_issue",
    "Consumer complaint narrative": "consumer_complaint_narrative",
    "Company public response": "company_public_response", "Company": "company",
    "State": "state", "ZIP code": "zip_code", "Tags": "tags", "Submitted via": "submitted_via",
    "Date sent to company": "date_sent_to_company",
    "Company response to consumer": "company_response", "Timely response?": "timely",
    "Complaint ID": "complaint_id",
}
DATA_COLS = list(RENAME.values())
# Columns an update may change. The narrative is handled separately (never overwritten by NULL).
COMPARE_COLS = [c for c in DATA_COLS if c not in ("complaint_id", "consumer_complaint_narrative")]


# ---------- database ----------
def connect(path=DB_PATH):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    cols = ",\n  ".join(f"{c} VARCHAR" for c in DATA_COLS if c != "complaint_id")
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS raw_complaints (
          complaint_id VARCHAR PRIMARY KEY,
          {cols},
          source VARCHAR,            -- where we first saw this complaint
          ingested_at TIMESTAMP,     -- first load
          updated_at TIMESTAMP       -- last time any field changed
        )""")
    # added later: tables created by an older version get the column too
    con.execute("ALTER TABLE raw_complaints ADD COLUMN IF NOT EXISTS missing_from_bulk BOOLEAN")
    con.execute("""
        CREATE TABLE IF NOT EXISTS ingest_state (
          source VARCHAR PRIMARY KEY, last_date_received VARCHAR, last_run TIMESTAMP, rows_seen BIGINT)""")
    return con


def upsert(con, df, source):
    """Insert new complaints, update changed ones. Returns (new, updated)."""
    df = df.reindex(columns=DATA_COLS).drop_duplicates("complaint_id", keep="last")
    df = df.astype(object).where(df.notna() & (df != ""), None)  # blanks -> NULL
    con.register("stg", df)
    new = con.execute("SELECT count(*) FROM stg WHERE complaint_id NOT IN (SELECT complaint_id FROM raw_complaints)").fetchone()[0]
    changed = " OR ".join(f"r.{c} IS DISTINCT FROM s.{c}" for c in COMPARE_COLS)
    changed += " OR (s.consumer_complaint_narrative IS NOT NULL AND r.consumer_complaint_narrative IS DISTINCT FROM s.consumer_complaint_narrative)"
    updated = con.execute(f"SELECT count(*) FROM stg s JOIN raw_complaints r USING (complaint_id) WHERE {changed}").fetchone()[0]

    cols = ", ".join(DATA_COLS)
    sets = ", ".join(f"{c} = excluded.{c}" for c in COMPARE_COLS)
    # COALESCE: a source without narratives (bulk/api) must never erase an existing narrative
    sets += ", consumer_complaint_narrative = COALESCE(excluded.consumer_complaint_narrative, raw_complaints.consumer_complaint_narrative)"
    where = " OR ".join(f"raw_complaints.{c} IS DISTINCT FROM excluded.{c}" for c in COMPARE_COLS)
    where += " OR (excluded.consumer_complaint_narrative IS NOT NULL AND raw_complaints.consumer_complaint_narrative IS DISTINCT FROM excluded.consumer_complaint_narrative)"
    con.execute(f"""
        INSERT INTO raw_complaints ({cols}, source, ingested_at, updated_at)
        SELECT {cols}, ?, now(), now() FROM stg
        ON CONFLICT (complaint_id) DO UPDATE SET {sets}, updated_at = now() WHERE {where}""", [source])
    con.unregister("stg")
    return new, updated


def mark_missing_from_bulk(con, bulk_df):
    """Flag complaints we hold that the latest bulk file no longer lists (within the bulk file's date range)."""
    ids = bulk_df[["complaint_id"]].drop_duplicates()
    con.register("bulk_ids", ids)
    con.execute("""
        UPDATE raw_complaints SET missing_from_bulk = (complaint_id NOT IN (SELECT complaint_id FROM bulk_ids))
        WHERE date_received >= ?""", [START_DATE])
    con.unregister("bulk_ids")
    n = con.execute("SELECT count(*) FROM raw_complaints WHERE missing_from_bulk").fetchone()[0]
    log.info("bulk: %d complaints are no longer listed in the bulk file (flagged missing_from_bulk)", n)


def save_state(con, source, rows_seen):
    last = con.execute("SELECT max(date_received) FROM raw_complaints").fetchone()[0]
    con.execute("INSERT OR REPLACE INTO ingest_state VALUES (?, ?, now(), ?)", [source, last, rows_seen])


def total_rows(con):
    return con.execute("SELECT count(*) FROM raw_complaints").fetchone()[0]


# ---------- sources ----------
def read_archive():
    """Narratives archive: monthly zip files, each holding one CSV (with multi-line narratives)."""
    parts = []
    for zp in sorted(glob.glob(ARCHIVE_GLOB)):
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                if name.lower().endswith(".csv"):
                    with z.open(name) as f:
                        df = pd.read_csv(f, dtype=str, keep_default_na=False)
                    parts.append(df[df["Company"] == COMPANY_FILTER])
    if not parts:
        raise SystemExit(f"No archive zips found at {ARCHIVE_GLOB}")
    return pd.concat(parts).rename(columns=RENAME)


def download_bulk():
    log.info("downloading bulk CSV (~355 MB)")
    with request_with_retry(BULK_URL, stream=True, timeout=120) as r, open(BULK_ZIP, "wb") as out:
        for chunk in r.iter_content(1 << 20):
            out.write(chunk)


def read_bulk():
    """Bulk CSV has no narratives, so no line breaks inside rows: we can filter raw lines
    by company *before* parsing, which is far faster than parsing 18M rows."""
    if not BULK_ZIP.exists():
        raise SystemExit(f"{BULK_ZIP} missing; run with --download")
    needle = COMPANY_FILTER.encode()
    with zipfile.ZipFile(BULK_ZIP) as z, z.open(z.namelist()[0]) as f:
        header = f.readline()
        lines = [ln for ln in f if needle in ln]
    df = pd.read_csv(io.BytesIO(header + b"".join(lines)), dtype=str, keep_default_na=False)
    df = df[df["Company"] == COMPANY_FILTER].rename(columns=RENAME)
    return df[df["date_received"] >= START_DATE]


def request_with_retry(url, params=None, attempts=4, timeout=60, **kw):
    """Timeout on every request; retry with a growing pause on network/server errors."""
    for i in range(1, attempts + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if i == attempts:
                raise
            wait = 2 ** i
            log.warning("request failed (%s); retry %d/%d in %ds", type(e).__name__, i, attempts - 1, wait)
            time.sleep(wait)


def read_api(since):
    """Live API: all Capital One complaints received on/after `since` (YYYY-MM-DD)."""
    base = {"company": COMPANY_FILTER, "size": API_PAGE, "sort": "created_date_desc",
            "no_aggs": "true", "field": "all", "date_received_min": since}
    rows, frm = [], 0
    while True:
        data = request_with_retry(API_URL, {**base, "frm": frm}).json()["hits"]
        if frm == 0 and data["total"]["value"] > API_MAX_WINDOW:
            raise SystemExit(f"{data['total']['value']:,} complaints since {since}: too many for the API; use `bulk`")
        rows += [h["_source"] for h in data["hits"]]
        frm += API_PAGE
        if frm >= data["total"]["value"] or not data["hits"]:
            break
    df = pd.DataFrame(rows)
    for c in ("date_received", "date_sent_to_company"):
        df[c] = df[c].str[:10]  # '2026-10-14T04:03:38.000Z' -> '2026-10-14' (same format as the CSVs)
    df["complaint_id"] = df["complaint_id"].astype(str)
    return df


# ---------- commands ----------
def run(source, download=False):
    con = connect()
    before = total_rows(con)
    if source == "archive":
        df = read_archive()
    elif source == "bulk":
        if download:
            download_bulk()
        df = read_bulk()
    else:
        wm = con.execute("SELECT max(date_received) FROM raw_complaints").fetchone()[0]
        if wm is None:
            raise SystemExit("raw_complaints is empty; run `archive` and `bulk` first")
        since = (date.fromisoformat(wm) - timedelta(days=OVERLAP_DAYS)).isoformat()
        df = read_api(since)
    new, updated = upsert(con, df, source)
    if source == "bulk":
        mark_missing_from_bulk(con, df)
    save_state(con, source, len(df))
    log.info("%s: fetched %s, %s new, %s updated | table rows %s -> %s",
             source, f"{len(df):,}", f"{new:,}", f"{updated:,}", f"{before:,}", f"{total_rows(con):,}")
    con.close()


def check():
    """Data check: complaints per month and per product; flag suspiciously empty months."""
    con = connect()
    n, nar = con.execute("SELECT count(*), count(consumer_complaint_narrative) FROM raw_complaints").fetchone()
    log.info("rows %s | with narrative %s (%.1f%%)", f"{n:,}", f"{nar:,}", 100 * nar / n)
    monthly = con.execute("SELECT substr(date_received,1,7) m, count(*) c FROM raw_complaints GROUP BY 1 ORDER BY 1").df()
    median = monthly["c"].iloc[:-1].median()  # last month is partial, leave it out of the median
    gaps = monthly.iloc[:-1][monthly["c"].iloc[:-1] < 0.5 * median]
    months = pd.period_range(monthly["m"].min(), monthly["m"].max(), freq="M").astype(str)
    missing = sorted(set(months) - set(monthly["m"]))
    log.info("months %s..%s | median/month %d | low months (<50%% of median): %s | missing months: %s",
             monthly["m"].iloc[0], monthly["m"].iloc[-1], median, gaps["m"].tolist() or "none", missing or "none")
    prod = con.execute("SELECT product, count(*) c FROM raw_complaints GROUP BY 1 ORDER BY 2 DESC LIMIT 6").fetchall()
    log.info("top products: %s", "; ".join(f"{p} {c:,}" for p, c in prod))
    con.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd in ("archive", "bulk", "api"):
        run(cmd, download="--download" in args)
    elif cmd == "check":
        check()
    else:
        raise SystemExit(__doc__)
