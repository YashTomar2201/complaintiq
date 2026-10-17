"""The shape of the AI's answer. Pydantic rejects anything that does not match (bad severity, unknown category...)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

ROOT_CAUSES = ["billing_error", "unauthorized_transaction", "fees_interest", "credit_reporting_error",
               "customer_service", "fraud_scam", "account_access", "payment_processing", "debt_collection", "other"]
REMEDIES = ["refund", "correction", "explanation", "close_account", "other"]


class Triage(BaseModel):
    summary: str = Field(description="1-2 sentence neutral summary of the complaint")
    root_cause: Literal["billing_error", "unauthorized_transaction", "fees_interest", "credit_reporting_error",
                        "customer_service", "fraud_scam", "account_access", "payment_processing",
                        "debt_collection", "other"]
    severity: int = Field(ge=1, le=5, description="1 = minor ... 5 = critical, see the rubric")
    monetary_harm_usd: Optional[float] = Field(default=None, ge=0, description="amount at stake if stated, else null")
    vulnerable_consumer: bool
    requested_remedy: Literal["refund", "correction", "explanation", "close_account", "other"]
    confidence: float = Field(ge=0, le=1)


# The rubric exactly as written in prompts/triage_v1.txt. The labeling page shows THIS to the human, so the
# human and the AI follow the same definitions (tests/test_eval.py checks the two stay in sync).
ROOT_CAUSE_HELP = {
    "billing_error": "wrong or duplicate charge, disputed purchase, payment applied wrongly on a statement",
    "unauthorized_transaction": "transactions the consumer did not make or approve (card or account)",
    "fees_interest": "annual, late, overdraft or other fees, interest rate or APR problems",
    "credit_reporting_error": "wrong or unfair information on a credit report, disputes with credit bureaus, hard inquiries",
    "customer_service": "rude, slow or unhelpful staff, unreturned calls, poor communication",
    "fraud_scam": "identity theft, scams, a fraudulent account opened in the consumer's name",
    "account_access": "account locked, closed or frozen, cannot log in, funds on hold, application denied",
    "payment_processing": "payments, deposits or transfers delayed, lost or misapplied",
    "debt_collection": "collection efforts, debt not owed, harassment by collectors",
    "other": "anything else",
}
SEVERITY_HELP = {
    5: "money lost or at risk AND (a vulnerable consumer OR a legal / regulator threat OR severe hardship such as being unable to pay rent or food)",
    4: "significant money lost (roughly $500 or more) or serious ongoing harm (e.g. identity theft, long account freeze), no vulnerability stated",
    3: "moderate problem: some money involved (under about $500) or a clear unresolved error that the bank has not fixed",
    2: "minor problem: small amounts, a delay or inconvenience, mostly resolved or easy to fix",
    1: "general dissatisfaction, question or opinion, no real harm or money involved",
}
VULNERABLE_HELP = ("true only if the text says or clearly shows the consumer is elderly or retired, a servicemember or veteran, "
                   "disabled or seriously ill, in financial hardship (job loss, cannot pay basic bills), or a victim of fraud or identity theft")
