"""Build clean tables/views from raw_complaints (runs models.sql) and record data-quality counts.

Usage: python -m src.transform.clean
"""
import logging
from pathlib import Path

from src.ingest.cfpb import connect

SQL_FILE = Path(__file__).with_name("models.sql")
log = logging.getLogger("clean")


def build(con):
    con.execute(SQL_FILE.read_text())
    n, uniq = con.execute("SELECT count(*), count(DISTINCT complaint_id) FROM complaints").fetchone()
    assert n == uniq, f"duplicate complaint_id in complaints: {n - uniq}"
    return n


def record_missing(con):
    """Missing-value count per column of the clean table, saved to dq_missing."""
    cols = [r[0] for r in con.execute("DESCRIBE complaints").fetchall()]
    sel = ", ".join(f"count(*) FILTER (WHERE {c} IS NULL) AS {c}" for c in cols)
    counts = con.execute(f"SELECT {sel} FROM complaints").fetchone()
    total = con.execute("SELECT count(*) FROM complaints").fetchone()[0]
    con.execute("CREATE OR REPLACE TABLE dq_missing (column_name VARCHAR, missing BIGINT, pct DOUBLE)")
    con.executemany("INSERT INTO dq_missing VALUES (?, ?, ?)",
                    [(c, m, round(100 * m / total, 2)) for c, m in zip(cols, counts) if m > 0])
    return con.execute("SELECT * FROM dq_missing ORDER BY missing DESC").fetchall()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    con = connect()
    n = build(con)
    missing = record_missing(con)
    log.info("complaints: %s rows, no duplicate complaint_id", f"{n:,}")
    log.info("missing values: %s", "; ".join(f"{c} {m:,} ({p}%)" for c, m, p in missing))
    for v in ("v_monthly_trends", "v_timeliness"):
        log.info("%s: %s rows", v, f"{con.execute(f'SELECT count(*) FROM {v}').fetchone()[0]:,}")
    con.close()
