"""Clean the messy CRM, then link CFPB complaints to CRM customers with simple scored rules.

Steps
  1. clean_crm   : fix ZIPs, parse 3 date formats, map product names to CFPB names, fill missing states
                   from ZIP, merge duplicate records into one customer  -> table crm_customers
  2. match       : state + 3-digit ZIP + product must agree and the account must be opened BEFORE the
                   complaint; extra points for an exact 5-digit ZIP and for opening in the 18 months
                   before the complaint                                  -> table complaint_matches
  3. evaluate    : compare with the planted answer key (data/crm_truth*.csv): precision and recall

Usage: python -m src.transform.match
"""
import logging
import re
from datetime import datetime

import pandas as pd

from src.ingest.cfpb import ROOT, connect
from src.ingest.fake_crm import NICKNAMES, TRUTH_CSV

log = logging.getLogger("match")

# normalised CRM product text -> CFPB product name
PRODUCT_MAP = {
    "cc": "Credit card", "creditcard": "Credit card", "caponecard": "Credit card",
    "chk": "Checking or savings account", "checking": "Checking or savings account",
    "dda": "Checking or savings account", "360checking": "Checking or savings account",
    "sav": "Checking or savings account", "savings": "Checking or savings account",
    "savingsacct": "Checking or savings account", "360savings": "Checking or savings account",
    "auto": "Vehicle loan or lease", "autoloan": "Vehicle loan or lease",
    "vehloan": "Vehicle loan or lease", "autofinance": "Vehicle loan or lease",
}
CANONICAL_FIRST = {v.lower(): k.lower() for k, v in NICKNAMES.items()}  # 'jon' -> 'jonathan'
RECENT_DAYS = 548  # "opened within ~18 months before the complaint" earns extra points

# score parts: 4 required agreements (state, zip3, product, opened before) + extras
SCORE_SQL = """
    4
    + CASE WHEN c.zip5 = k.zip5 THEN 2 ELSE 0 END
    + CASE WHEN date_diff('day', k.open_date, c.date_received) <= {recent} THEN 2 ELSE 0 END"""


# ---------- cleaning helpers (small, so they can be unit-tested) ----------
def clean_zip(z):
    """'2134' -> '02134', '19343-4631' -> '19343', '12345.0' -> '12345'."""
    if z is None or pd.isna(z):
        return None
    z = str(z).strip().split("-")[0]
    z = re.sub(r"\.0+$", "", z)
    return z.zfill(5) if z.isdigit() and len(z) <= 5 else None


def parse_date(s):
    """Accepts '2021-03-05', '03/05/2021' and 'Mar 5, 2021'."""
    if s is None or pd.isna(s):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except ValueError:
            pass
    return None


def name_parts(name):
    """'SMITH, JONATHAN' / 'Jon Smith' / 'J. Smith' -> (last, canonical first initial)."""
    name = re.sub(r"[.]", "", str(name)).strip().lower()
    if "," in name:
        last, first = [p.strip() for p in name.split(",", 1)]
    else:
        first, _, last = name.partition(" ")
    first = CANONICAL_FIRST.get(first, first)
    return last, first[:1]


def map_product(p):
    return PRODUCT_MAP.get(re.sub(r"[^a-z0-9]", "", str(p).lower()))


# ---------- step 1: clean the CRM ----------
def clean_crm(con):
    crm = con.execute("SELECT * FROM crm_raw").df()
    out = pd.DataFrame({
        "record_id": crm.record_id,
        "zip5": crm["zip"].map(clean_zip),
        "open_date": crm.account_opened.map(parse_date),
        "product": crm["product"].map(map_product),
        "state": crm.state.replace("", None),
    })
    parts = crm.customer_name.map(name_parts)
    out["last"], out["first_initial"] = [p[0] for p in parts], [p[1] for p in parts]

    # fill missing state from the ZIP's first 3 digits (most common state among complaints)
    zip3_state = con.execute("""
        SELECT zip3, arg_max(state, n) AS state FROM
          (SELECT zip3, state, count(*) n FROM complaints WHERE zip3 IS NOT NULL AND state IS NOT NULL GROUP BY 1, 2)
        GROUP BY zip3""").df().set_index("zip3").state
    out["state_imputed"] = out.state.isna()
    out["state"] = out.state.fillna(out.zip5.str[:3].map(zip3_state))

    # merge duplicates: same last name + first initial + ZIP + product + open date = same customer
    key = ["last", "first_initial", "zip5", "product", "open_date"]
    out["customer_id"] = out.groupby(key, dropna=False).record_id.transform("min")
    cust = (out.sort_values("record_id").groupby("customer_id", as_index=False)
            .agg(state=("state", "first"), zip5=("zip5", "first"), product=("product", "first"),
                 open_date=("open_date", "first"), n_records=("record_id", "count"),
                 record_ids=("record_id", list)))
    stats = dict(records=len(out), customers=len(cust), merged=len(out) - len(cust),
                 bad_zip=int(out.zip5.isna().sum()), bad_date=int(out.open_date.isna().sum()),
                 unmapped_product=int(out["product"].isna().sum()),
                 state_filled=int((out.state_imputed & out.state.notna()).sum()),
                 state_still_missing=int(out.state.isna().sum()))
    con.register("cust_df", cust.drop(columns="record_ids").assign(record_ids=cust.record_ids.map(",".join)))
    con.execute("CREATE OR REPLACE TABLE crm_customers AS SELECT * FROM cust_df")
    con.unregister("cust_df")
    return stats


# ---------- step 2: match ----------
def match(con):
    score = SCORE_SQL.format(recent=RECENT_DAYS)
    # (a) LOOSE: best candidate for each complaint (ties broken arbitrarily by customer_id)
    con.execute(f"""
        CREATE OR REPLACE TABLE complaint_matches_loose AS
        WITH cand AS (
            SELECT c.complaint_id, k.customer_id, {score} AS score
            FROM complaints c
            JOIN crm_customers k
              ON c.state = k.state AND c.zip3 = substr(k.zip5, 1, 3) AND c.product = k.product
             AND k.open_date < c.date_received
        ), ranked AS (
            SELECT *, row_number() OVER (PARTITION BY complaint_id ORDER BY score DESC, customer_id) AS rn,
                   count(*) OVER (PARTITION BY complaint_id) AS n_candidates,
                   count(*) OVER (PARTITION BY complaint_id, score) AS n_same_score
            FROM cand)
        SELECT complaint_id, customer_id, score AS confidence, n_candidates, (n_same_score > 1) AS tie
        FROM ranked WHERE rn = 1""")
    # (b) ONE-TO-ONE: a customer should not be linked to many complaints. Keep each customer's
    #     best-scoring complaint; any tie (customer or complaint side) is flagged `ambiguous`
    #     and goes to human review instead of being trusted.
    con.execute("""
        CREATE OR REPLACE TABLE complaint_matches AS
        WITH o AS (
            SELECT *, row_number() OVER (PARTITION BY customer_id ORDER BY confidence DESC, complaint_id) AS crn,
                   count(*) OVER (PARTITION BY customer_id, confidence) AS n_same_cust_score
            FROM complaint_matches_loose)
        SELECT complaint_id, customer_id, confidence, n_candidates, (tie OR n_same_cust_score > 1) AS ambiguous
        FROM o WHERE crn = 1""")


# ---------- step 3: evaluate ----------
def evaluate(con):
    """Precision = of the matches we made, how many are right. Recall = of the 300 planted, how many we found."""
    truth = pd.read_csv(TRUTH_CSV, dtype=str)
    rec2ent = pd.read_csv(TRUTH_CSV.with_name("crm_truth_records.csv"), dtype=str).set_index("record_id").entity_id
    cust = con.execute("SELECT customer_id, record_ids FROM crm_customers").df()
    cust["entity_id"] = cust.record_ids.str.split(",").str[0].map(rec2ent)
    pairs = set(zip(truth.entity_id, truth.complaint_id))

    def load(table, where="true"):
        m = con.execute(f"SELECT * FROM {table} WHERE {where}").df().merge(cust[["customer_id", "entity_id"]], on="customer_id")
        m["correct"] = [(e, c) in pairs for e, c in zip(m.entity_id, m.complaint_id)]
        return m

    configs = [
        ("Loose: best customer per complaint, any score", load("complaint_matches_loose"), 4),
        ("One-to-one, ties excluded, score >= 4", load("complaint_matches", "NOT ambiguous"), 4),
        ("One-to-one, ties excluded, score >= 8 (strict)", load("complaint_matches", "NOT ambiguous"), 8),
    ]
    rows = []
    for name, m, t in configs:
        sel = m[m.confidence >= t]
        tp = int(sel.correct.sum())
        rows.append(dict(rule=name, matches=len(sel), correct=tp,
                         precision=round(100 * tp / len(sel), 1), recall=round(100 * tp / len(truth), 1)))
    amb = load("complaint_matches", "ambiguous")
    info = dict(true_people=rec2ent.nunique(), customers_after_merge=len(cust), planted=len(truth),
                ambiguous=len(amb), ambiguous_correct=int(amb.correct.sum()))
    return pd.DataFrame(rows), info


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    con = connect()
    s = clean_crm(con)
    log.info("crm cleaned: %s", ", ".join(f"{k}={v:,}" for k, v in s.items()))
    match(con)
    table, d = evaluate(con)
    log.info("duplicates merged to %s customers (true people: %s)", f"{d['customers_after_merge']:,}", f"{d['true_people']:,}")
    log.info("vs %d planted matches:\n%s", d["planted"], table.to_string(index=False))
    log.info("%d ambiguous links sent to review (%d of them were actually right)", d["ambiguous"], d["ambiguous_correct"])
    con.close()
