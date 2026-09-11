import json
from datetime import datetime
from pathlib import Path
from models import PaymentRequest
import os

AUDIT_LOG_FILE = "audit_log.jsonl"


def log_transaction(
    request: PaymentRequest,
    recipient_verification: dict,
    risk_factors: list,
    llm_reasoning: str,
    final_score: float,
    category: str,
    action: str,
    outcome: str,
) -> None:
    """
    Append transaction to audit log (JSONL format).
    """
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "request": {
            "sender_id": request.sender_id,
            "recipient_name": request.recipient_name,
            "recipient_id": request.recipient_id,
            "amount": request.amount,
            "note": request.note,
        },
        "recipient_verification": recipient_verification,
        "risk_factors": risk_factors,
        "llm_reasoning": llm_reasoning,
        "final_score": final_score,
        "category": category,
        "action": action,
        "outcome": outcome,
    }

    try:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"✓ Logged transaction: {request.recipient_name} - {outcome.upper()}")
    except Exception as e:
        print(f"⚠ Failed to log transaction: {str(e)}")


def get_audit_history(limit: int = 50) -> list:
    """
    Retrieve recent audit log entries.
    """
    if not Path(AUDIT_LOG_FILE).exists():
        return []

    entries = []
    with open(AUDIT_LOG_FILE, "r") as f:
        for line in f:
            entries.append(json.loads(line))

    return entries[-limit:]
