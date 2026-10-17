import pandas as pd

from src.ingest.cfpb import connect, total_rows, upsert


def make(cid, narrative=None, response="In progress"):
    row = {c: "x" for c in
           ["date_received", "product", "sub_product", "issue", "sub_issue", "company_public_response", "company",
            "state", "zip_code", "tags", "submitted_via", "date_sent_to_company", "timely"]}
    return {**row, "complaint_id": cid, "consumer_complaint_narrative": narrative, "company_response": response}


def test_upsert_twice_creates_no_duplicates(tmp_path):
    con = connect(tmp_path / "t.duckdb")
    df = pd.DataFrame([make("1", "text"), make("2")])
    assert upsert(con, df, "archive") == (2, 0)
    assert upsert(con, df, "archive") == (0, 0)
    assert total_rows(con) == 2


def test_update_changes_status_but_keeps_narrative(tmp_path):
    con = connect(tmp_path / "t.duckdb")
    upsert(con, pd.DataFrame([make("1", "my story")]), "archive")
    # the bulk file has no narrative but a newer status
    new, updated = upsert(con, pd.DataFrame([make("1", None, "Closed with explanation")]), "bulk")
    assert (new, updated) == (0, 1)
    row = con.execute("SELECT company_response, consumer_complaint_narrative FROM raw_complaints").fetchone()
    assert row == ("Closed with explanation", "my story")
