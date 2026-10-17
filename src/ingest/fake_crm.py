"""Generate a deliberately MESSY fake internal CRM (Faker) and plant known true matches.

We have no access to Capital One's real customer database, so we simulate one. Mess added on purpose:
  - duplicate customers with different name styles ("Jon Smith" / "SMITH, JONATHAN")
  - ZIP codes saved as numbers (leading zero lost: 02134 -> 2134), some ZIP+4
  - account-open dates in 3 formats
  - ~5% missing states
  - product names that differ from the CFPB's ("CC", "DDA", "Veh Loan"...)
PLANTED_MATCHES real complaints each get one CRM customer whose state, ZIP, product and timing line up.
The answer key goes to a SEPARATE file (data/crm_truth.csv) that the cleaning/matching code never reads;
only the evaluation step does.

Usage: python -m src.ingest.fake_crm
"""
import logging
import random
from datetime import date, timedelta

import pandas as pd
from faker import Faker

from src.ingest.cfpb import ROOT, connect

SEED = 42
N_ENTITIES = 4700          # distinct people (incl. planted ones)
PLANTED_MATCHES = 300
SHARE_PLANTED_MASKED_ZIP = 0.2   # planted complaints whose public ZIP is masked ('604XX'): harder to match
N_DUPLICATES = 400         # extra records for people already in the CRM
SHARE_BACKGROUND_NEAR_COMPLAINT_ZIP = 0.10  # background customers living in a ZIP that has complaints
MISSING_STATE_RATE = 0.05
# Simulation assumption: planted customers complain 30-540 days after opening the account.
PLANT_DAYS_BEFORE = (30, 540)

CRM_CSV = ROOT / "data" / "fake_crm.csv"
TRUTH_CSV = ROOT / "data" / "crm_truth.csv"
log = logging.getLogger("fake_crm")

# CRM product label -> (list of messy spellings). The matcher must map these back to CFPB names.
MESSY_PRODUCT = {
    "Credit card": ["CC", "Credit Card", "CREDIT CARD", "Cap One Card", "cc"],
    "Checking or savings account": [],  # filled per sub-type below
    "Vehicle loan or lease": ["Auto", "Auto Loan", "VEH LOAN", "Auto Finance"],
}
CHECKING = ["Chk", "Checking", "DDA", "360 Checking"]
SAVINGS = ["Sav", "Savings", "Savings Acct", "360 Savings"]

NICKNAMES = {"Jonathan": "Jon", "Michael": "Mike", "William": "Bill", "Robert": "Bob", "James": "Jim",
             "Elizabeth": "Liz", "Katherine": "Kate", "Christopher": "Chris", "Matthew": "Matt",
             "Joseph": "Joe", "Richard": "Rick", "Thomas": "Tom", "Daniel": "Dan", "David": "Dave",
             "Jennifer": "Jen", "Margaret": "Peggy", "Patricia": "Pat", "Steven": "Steve", "Andrew": "Andy"}


def messy_date(d, rng):
    """Same date, one of 3 formats."""
    f = rng.choice(["iso", "us", "long"])
    if f == "iso":
        return d.isoformat()
    if f == "us":
        return d.strftime("%m/%d/%Y")
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def messy_zip(zip5, rng):
    """Spreadsheet-style damage: stored as a number (leading zero lost), sometimes ZIP+4."""
    r = rng.random()
    if r < 0.05:
        return f"{zip5}-{rng.randint(1000, 9999)}"
    return str(int(zip5))


def name_variant(first, last, rng):
    """A different way of writing the same person's name (used for duplicate records)."""
    options = [f"{last.upper()}, {first.upper()}", f"{last}, {first}"]
    options.append(f"{NICKNAMES[first]} {last}" if first in NICKNAMES else f"{first[0]}. {last}")
    return rng.choice(options)


def build():
    rng = random.Random(SEED)
    fake = Faker("en_US")
    Faker.seed(SEED)
    con = connect()
    comp = con.execute("""
        SELECT complaint_id, date_received, product, sub_product, state, zip5, zip3
        FROM complaints
        WHERE product IN ('Credit card', 'Checking or savings account', 'Vehicle loan or lease')
          AND state IS NOT NULL AND zip3 IS NOT NULL""").df()
    all_zips = con.execute("SELECT DISTINCT zip5, state FROM complaints WHERE zip5 IS NOT NULL AND state IS NOT NULL").df()

    # ---- planted entities: one real complaint each
    n_masked = int(PLANTED_MATCHES * SHARE_PLANTED_MASKED_ZIP)
    full = comp[comp.zip5.notna()].sample(PLANTED_MATCHES - n_masked, random_state=SEED)
    masked = comp[comp.zip5.isna()].sample(n_masked, random_state=SEED)
    planted = pd.concat([full, masked])
    entities = []
    for r in planted.itertuples():
        zip5 = r.zip5 if pd.notna(r.zip5) else r.zip3 + f"{rng.randint(0, 99):02d}"
        opened = r.date_received.date() - timedelta(days=rng.randint(*PLANT_DAYS_BEFORE))
        entities.append(dict(complaint_id=r.complaint_id, state=r.state, zip5=zip5,
                             cfpb_product=r.product, sub_product=r.sub_product, opened=opened))

    # ---- background customers: nothing to do with any specific complaint
    n_bg = N_ENTITIES - PLANTED_MATCHES
    products = ["Credit card"] * 55 + ["Checking or savings account"] * 35 + ["Vehicle loan or lease"] * 10
    for _ in range(n_bg):
        if rng.random() < SHARE_BACKGROUND_NEAR_COMPLAINT_ZIP:
            z = all_zips.sample(1, random_state=rng.randint(0, 10**9)).iloc[0]
            state, zip5 = z.state, z.zip5
        else:
            state = fake.state_abbr()
            zip5 = f"{rng.randint(1000, 99950):05d}"
        opened = date(2008, 1, 1) + timedelta(days=rng.randint(0, (date(2026, 9, 30) - date(2008, 1, 1)).days))
        entities.append(dict(complaint_id=None, state=state, zip5=zip5,
                             cfpb_product=rng.choice(products), sub_product=None, opened=opened))
    rng.shuffle(entities)

    # ---- turn entities into CRM records (+ duplicates)
    records, truth_rec, truth_match = [], [], []
    def product_label(e):
        if e["cfpb_product"] == "Checking or savings account":
            sav = (e["sub_product"] == "Savings account") if e["sub_product"] else rng.random() < 0.3
            return rng.choice(SAVINGS if sav else CHECKING)
        return rng.choice(MESSY_PRODUCT[e["cfpb_product"]])

    def add_record(ent_id, e, first, last, as_variant):
        rec_id = f"CRM-{len(records) + 1:06d}"
        name = name_variant(first, last, rng) if as_variant else f"{first} {last}"
        state = "" if rng.random() < MISSING_STATE_RATE else e["state"]
        records.append(dict(record_id=rec_id, customer_name=name, state=state, zip=messy_zip(e["zip5"], rng),
                            product=product_label(e), account_opened=messy_date(e["opened"], rng)))
        truth_rec.append(dict(record_id=rec_id, entity_id=ent_id))

    names = {}
    for i, e in enumerate(entities):
        ent_id = f"E{i + 1:05d}"
        names[ent_id] = (fake.first_name(), fake.last_name())
        add_record(ent_id, e, *names[ent_id], as_variant=False)
        if e["complaint_id"]:
            truth_match.append(dict(entity_id=ent_id, complaint_id=e["complaint_id"]))
    for i in rng.sample(range(len(entities)), N_DUPLICATES):
        ent_id = f"E{i + 1:05d}"
        add_record(ent_id, entities[i], *names[ent_id], as_variant=True)

    crm = pd.DataFrame(records).sample(frac=1, random_state=SEED)  # shuffle so duplicates are not adjacent
    crm.to_csv(CRM_CSV, index=False)
    pd.DataFrame(truth_match).to_csv(TRUTH_CSV, index=False)
    pd.DataFrame(truth_rec).to_csv(TRUTH_CSV.with_name("crm_truth_records.csv"), index=False)
    # load as-is (all text) into DuckDB, like ingesting a CSV export from a customer system
    con.execute("CREATE OR REPLACE TABLE crm_raw AS SELECT * FROM read_csv(?, all_varchar=true)", [str(CRM_CSV)])
    n = con.execute("SELECT count(*) FROM crm_raw").fetchone()[0]
    con.close()
    log.info("crm_raw: %s records for %s people (%d duplicates), %d planted true matches",
             f"{n:,}", f"{len(entities):,}", N_DUPLICATES, len(truth_match))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    build()
