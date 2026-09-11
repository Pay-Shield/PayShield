from models import PaymentRequest, ModuleOutput
from typing import Optional
import re


KNOWN_RECIPIENTS = {
    "GOOG": {"name": "Google Pay", "account_age_days": 365},
    "AMZN": {"name": "Amazon Payments", "account_age_days": 300},
    "UTIL": {"name": "Utility Payments", "account_age_days": 200},
}

FLAGGED_RECIPIENTS = {
    "SCAM001": "Known scam ring",
    "FRAUD_NET": "Compromised account history",
}

URGENCY_KEYWORDS = {"urgent", "immediately", "expiring", "asap", "hurry", "quickly", "time-sensitive"}
IMPERSONATION_KEYWORDS = {"bank", "support", "kyc", "refund", "otp", "verify", "confirm identity", "security"}
GIFT_CARD_KEYWORDS = {"gift card", "itunes", "google play", "amazon voucher", "recharge", "crypto"}


def recipient_verification(request: PaymentRequest, user_transaction_history: Optional[dict] = None) -> dict:
    """
    Verify recipient: known/new/flagged status, account format validation.
    """
    recipient_id = request.recipient_id.upper()

    if recipient_id in FLAGGED_RECIPIENTS:
        return {
            "status": "flagged",
            "reason": FLAGGED_RECIPIENTS[recipient_id],
            "score_contribution": 45,
        }

    if recipient_id in KNOWN_RECIPIENTS:
        recipient_info = KNOWN_RECIPIENTS[recipient_id]
        return {
            "status": "known",
            "name": recipient_info["name"],
            "account_age_days": recipient_info["account_age_days"],
            "score_contribution": 0,
        }

    # Validate basic ID format (simple alphanumeric check)
    if not re.match(r"^[A-Z0-9]{3,}$", recipient_id):
        return {
            "status": "invalid_format",
            "score_contribution": 20,
        }

    return {
        "status": "new",
        "score_contribution": 25,
    }


def risk_analysis_rules(request: PaymentRequest, user_baseline: Optional[float] = None) -> dict:
    """
    Rule-based risk analysis: amount, velocity, keyword hits.
    """
    score = 0
    factors = []

    # Amount vs baseline (default baseline = 1000)
    baseline = user_baseline or 1000.0
    if request.amount > baseline * 5:
        score += 30
        factors.append({
            "type": "amount_5x_baseline",
            "value": request.amount,
            "baseline": baseline,
            "weight": 30,
        })
    elif request.amount > baseline * 2:
        score += 15
        factors.append({
            "type": "amount_2_5x_baseline",
            "value": request.amount,
            "baseline": baseline,
            "weight": 15,
        })

    # Keyword analysis
    note_lower = request.note.lower()

    urgency_hits = URGENCY_KEYWORDS & set(note_lower.split())
    if urgency_hits:
        weight = min(30, 15 + len(urgency_hits) * 5)
        score += weight
        factors.append({
            "type": "urgency_language",
            "keywords": list(urgency_hits),
            "weight": weight,
        })

    impersonation_hits = IMPERSONATION_KEYWORDS & set(note_lower.split())
    if impersonation_hits:
        score += 25
        factors.append({
            "type": "impersonation_language",
            "keywords": list(impersonation_hits),
            "weight": 25,
        })

    gift_card_hits = GIFT_CARD_KEYWORDS & set(note_lower.split())
    if gift_card_hits:
        score += 30
        factors.append({
            "type": "gift_card_request",
            "keywords": list(gift_card_hits),
            "weight": 30,
        })

    return {
        "score": min(score, 100),
        "factors": factors,
    }


def behavioral_pattern(request: PaymentRequest, user_session_history: Optional[list] = None) -> dict:
    """
    Behavioral: velocity (new recipients in session), amount deviation.
    """
    score = 0
    factors = []

    # Velocity check: count new recipients attempted in this session
    if user_session_history:
        new_recipient_count = sum(
            1 for req in user_session_history
            if req.get("recipient_status") == "new"
        )
        if new_recipient_count >= 2:
            score += 15
            factors.append({
                "type": "high_velocity",
                "new_recipients_in_session": new_recipient_count,
                "weight": 15,
            })

    return {
        "score": score,
        "factors": factors,
    }
