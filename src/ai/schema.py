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
