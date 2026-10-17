"""Tests for the dashboard view and the plain-English insights, using a small synthetic dataset."""
import datetime as dt

import pandas as pd
import pytest

from src.app.db import run_sql
from src.app.insights import compute, last_complete_month
from src.ingest.cfpb import connect, upsert
from src.transform.clean import build


def make_rows():
    """8 full months of 2025. Credit card doubles in Jun-Aug (half of it a new issue); Debt collection is steady."""
    rows, n = [], 0
    for month in range(1, 9):
        spec = [("Credit card", 120 if month <= 5 else 240), ("Debt collection", 110)]
        for product, count in spec:
            for i in range(count):
                n += 1
                issue = "Fees or interest" if (product == "Credit card" and month >= 6 and i % 2) else "Managing an account"
                relief = "Closed with monetary relief" if (product == "Credit card" and i % 10 == 0) else "Closed with explanation"
                rows.append(dict(
                    complaint_id=str(n), date_received=f"2025-{month:02d}-{1 + i % 28:02d}", product=product,
                    sub_product=None, issue=issue, sub_issue=None, consumer_complaint_narrative=None,
                    company_public_response=None, company="CAPITAL ONE FINANCIAL CORPORATION", state="TX",
                    zip_code="75001", tags=None, submitted_via="Web", date_sent_to_company=f"2025-{month:02d}-01",
                    company_response=relief, timely="Yes"))
    return rows


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    con = connect(tmp_path_factory.mktemp("db") / "t.duckdb")
    upsert(con, pd.DataFrame(make_rows()), "archive")
    build(con)
    return con


@pytest.fixture
def f():
    return dict(start=dt.date(2025, 1, 1), end=dt.date(2025, 8, 31), products=["Credit card", "Debt collection"], states=["TX"])


def test_facts_view_matches_phase3_views(con):
    """The dashboard view and the Phase 3 trend view must agree: one version of the truth."""
    a = con.execute("SELECT year_month, product, sum(complaints) FROM v_dashboard_facts GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
    b = con.execute("SELECT year_month, product, complaints FROM v_monthly_trends ORDER BY 1, 2").fetchall()
    assert a == b


def test_last_complete_month():
    assert last_complete_month(dt.date(2025, 8, 31)) == pd.Timestamp("2025-08-01")  # month fully covered
    assert last_complete_month(dt.date(2025, 10, 14)) == pd.Timestamp("2025-09-01")  # October is partial


def test_trend_insight_names_product_change_and_driver(con, f):
    text = compute(lambda s, p=None: run_sql(con, s, p), f, f["end"])[0]
    assert "Credit card complaints rose 100% (360 to 720)" in text
    assert "driven by 'Fees or interest' (+360)" in text


def test_relief_and_peak_insights(con, f):
    peak, relief = compute(lambda s, p=None: run_sql(con, s, p), f, f["end"])[1:]
    assert "busiest month" in peak or "steady" in peak
    assert "of closed complaints ended with monetary relief" in relief and "Credit card" in relief


def test_filters_change_insights_and_handle_short_ranges(con, f):
    run = lambda s, p=None: run_sql(con, s, p)
    short = compute(run, {**f, "start": dt.date(2025, 6, 1)}, f["end"])
    assert short[0].startswith("Not enough history")
    only_debt = compute(run, {**f, "products": ["Debt collection"]}, f["end"])
    assert "Debt collection complaints" in only_debt[0] and "0%" in only_debt[0]
