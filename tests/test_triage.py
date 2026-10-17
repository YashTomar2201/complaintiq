"""AI triage tests use a fake LLM, so they cost nothing and need no API key."""
import json

import pandas as pd
import pytest
from pydantic import ValidationError

from src.ai import triage
from src.ai.llm import LLMResult
from src.ai.pii import mask_pii
from src.ai.schema import Triage
from src.ingest.cfpb import connect, upsert
from src.transform.clean import build

GOOD = {"summary": "Charged twice.", "root_cause": "billing_error", "severity": 3, "monetary_harm_usd": 89.99,
        "vulnerable_consumer": False, "requested_remedy": "refund", "confidence": 0.9}


class FakeClient:
    model_name = "fake-model"

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def complete(self, system, user, schema):
        self.calls += 1
        return LLMResult(self.replies.pop(0) if self.replies else json.dumps(GOOD), 100, 20)


def raw_row(cid, narrative):
    return dict(complaint_id=cid, date_received="2025-03-10", product="Credit card", sub_product=None,
                issue="Managing an account", sub_issue=None, consumer_complaint_narrative=narrative,
                company_public_response=None, company="CAPITAL ONE FINANCIAL CORPORATION", state="MA",
                zip_code="02134", tags=None, submitted_via="Web", date_sent_to_company="2025-03-10",
                company_response="Closed with explanation", timely="Yes")


@pytest.fixture
def con(tmp_path, monkeypatch):
    path = tmp_path / "t.duckdb"
    con = connect(path)
    upsert(con, pd.DataFrame([raw_row(str(i), f"Complaint text number {i} {{$50.00}}") for i in range(1, 6)]), "archive")
    build(con)
    con.close()
    monkeypatch.setattr(triage, "connect", lambda: connect(path))
    con = connect(path)
    triage.make_sample(con, 5)
    return con


def test_schema_rejects_bad_output():
    assert Triage.model_validate(GOOD).severity == 3
    for bad in ({**GOOD, "severity": 9}, {**GOOD, "root_cause": "made_up"}, {**GOOD, "confidence": 1.5}):
        with pytest.raises(ValidationError):
            Triage.model_validate(bad)


def test_prompt_survives_curly_braces():
    out = triage.build_prompt("A {product} B {issue} C {narrative} {$1}", "Credit card", "Fees", "paid {$5.00}")
    assert out == "A Credit card B Fees C paid {$5.00} {$1}"


def test_pii_masking_removes_contact_details():
    masked, found = mask_pii("Call me at 555-201-3344 or jc@example.com about account 123456789012. Paid {$1,200.50}.")
    assert "555-201-3344" not in masked and "jc@example.com" not in masked and "123456789012" not in masked
    assert "{$1,200.50}" in masked  # amounts are kept: they matter for severity
    assert found["EMAIL_ADDRESS"] == 1


def test_run_is_idempotent_and_saves_traceability(con):
    client = FakeClient([])
    triage.run("v1", client=client)
    triage.run("v1", client=client)  # second run finds nothing left to do
    assert client.calls == 5
    rows = con.execute("SELECT status, model_name, prompt_version, severity FROM complaint_triage").fetchall()
    assert len(rows) == 5 and set(rows) == {("ok", "fake-model", "v1", 3)}


class PickyClient(FakeClient):
    """Complaint 1: invalid once, then valid (the retry rescues it). Complaint 2: always invalid. Others: valid."""

    def __init__(self):
        super().__init__([])
        self.seen = {}

    def complete(self, system, user, schema):
        self.calls += 1
        n = "1" if "number 1 " in user else "2" if "number 2 " in user else "x"
        self.seen[n] = self.seen.get(n, 0) + 1
        if n == "2" or (n == "1" and self.seen[n] == 1):
            return LLMResult("not json", 100, 20)
        return LLMResult(json.dumps(GOOD), 100, 20)


def test_invalid_output_is_retried_once_then_marked_failed(con):
    triage.run("v1", client=PickyClient())
    status = dict(con.execute("SELECT complaint_id, status FROM complaint_triage").fetchall())
    assert status["1"] == "ok" and status["2"] == "failed"
    assert con.execute("SELECT error FROM complaint_triage WHERE complaint_id = '2'").fetchone()[0]
    # failed rows are retried on the next run, ok rows are not
    again = FakeClient([])
    triage.run("v1", client=again)
    assert again.calls == 1 and con.execute("SELECT status FROM complaint_triage WHERE complaint_id = '2'").fetchone()[0] == "ok"
