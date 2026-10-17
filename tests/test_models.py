"""Tests for the clean `complaints` table, built from a tiny hand-made raw table (no real data needed)."""
import pandas as pd
import pytest

from src.ingest.cfpb import connect, upsert
from src.transform.clean import build

COLS = ["date_received", "product", "sub_product", "issue", "sub_issue", "consumer_complaint_narrative",
        "company_public_response", "company", "state", "zip_code", "tags", "submitted_via",
        "date_sent_to_company", "company_response", "timely"]


def row(cid, **kw):
    base = dict(date_received="2025-03-10", product="Credit card", sub_product="Store credit card",
                issue="Managing an account", sub_issue=None, consumer_complaint_narrative=None,
                company_public_response=None, company="CAPITAL ONE FINANCIAL CORPORATION", state="MA",
                zip_code="02134", tags=None, submitted_via="Web", date_sent_to_company="2025-03-10",
                company_response="Closed with explanation", timely="Yes")
    return {"complaint_id": cid, **base, **kw}


@pytest.fixture
def con(tmp_path):
    con = connect(tmp_path / "t.duckdb")
    rows = [
        row("1", zip_code="02134", tags="Older American, Servicemember",
            consumer_complaint_narrative="Charged  {$1,200.50} twice\nand {$30} fee."),
        row("2", zip_code="604XX", sub_product="I do not know", timely="No",
            company_response="In progress", consumer_complaint_narrative="same text", date_received="2025-03-01"),
        row("3", zip_code="XXXXX", state=None, consumer_complaint_narrative="same text"),
        row("4", zip_code=None),
    ]
    upsert(con, pd.DataFrame(rows), "archive")
    build(con)
    return con


def get(con, col, cid):
    return con.execute(f"SELECT {col} FROM complaints WHERE complaint_id = ?", [cid]).fetchone()[0]


def test_one_row_per_complaint(con):
    assert con.execute("SELECT count(*) FROM complaints").fetchone()[0] == 4


def test_zip_forms_keep_leading_zero_and_masking(con):
    assert get(con, "zip5", "1") == "02134"          # text, leading zero kept
    assert get(con, "zip5", "2") is None and get(con, "zip3", "2") == "604" and get(con, "zip_masked", "2")
    assert get(con, "zip3", "3") is None              # fully masked: no usable prefix
    assert get(con, "zip3", "4") is None and not get(con, "zip_masked", "4")


def test_flags_and_types(con):
    assert get(con, "is_older_american", "1") and get(con, "is_servicemember", "1")
    assert not get(con, "is_older_american", "4")
    assert get(con, "timely", "2") is False and get(con, "timely", "1") is True
    assert get(con, "is_final_response", "2") is False
    assert get(con, "sub_product", "2") is None       # 'I do not know' -> NULL
    assert str(get(con, "year_month", "1")) == "2025-03"


def test_narrative_helpers(con):
    assert get(con, "narrative", "1") == "Charged {$1,200.50} twice and {$30} fee."  # whitespace collapsed
    assert get(con, "amounts_usd", "1") == [1200.5, 30.0]
    assert get(con, "narrative_copies", "2") == 2
    assert get(con, "is_first_copy", "2") is True and get(con, "is_first_copy", "3") is False  # 2 is earlier
    assert get(con, "is_first_copy", "4") is False    # no narrative


def test_missing_from_bulk_defaults_false(con):
    assert get(con, "missing_from_bulk", "1") is False


def test_views_exist(con):
    assert con.execute("SELECT sum(complaints) FROM v_monthly_trends").fetchone()[0] == 4
    assert con.execute("SELECT min(timely_pct) FROM v_timeliness").fetchone()[0] is not None
