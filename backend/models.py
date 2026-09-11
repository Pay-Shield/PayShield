from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class RiskCategory(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionType(str, Enum):
    AUTO_APPROVE = "auto_approve"
    REQUIRE_CONFIRMATION = "require_confirmation"
    REQUIRE_VERIFICATION = "require_verification"
    HARD_BLOCK = "hard_block"


class PaymentRequest(BaseModel):
    sender_id: str
    recipient_name: str
    recipient_id: str
    amount: float
    note: str


class ModuleOutput(BaseModel):
    module_name: str
    score_contribution: float
    explanation: dict


class RiskAnalysisResult(BaseModel):
    risk_score: float
    category: RiskCategory
    action: ActionType
    factors: list[dict]
    llm_reasoning: str
    confidence: float


class AuditLogEntry(BaseModel):
    timestamp: datetime
    request: PaymentRequest
    recipient_verification: dict
    risk_factors: list[dict]
    llm_reasoning: str
    final_score: float
    category: RiskCategory
    action: ActionType
    outcome: str  # "completed", "halted", "cancelled"


class UserConfirmation(BaseModel):
    confirmed: bool
    verification_passed: Optional[bool] = None
