import os
import json
import re
from anthropic import Anthropic
from models import PaymentRequest


def classify_fraud_intent(
    request: PaymentRequest,
    recipient_status: str,
    rule_score: float,
) -> dict:
    """
    Use Nemotron (lightweight) for fast fraud classification and intent extraction.
    Returns score adjustment and detected risk factors.
    """
    # For now, use heuristic rules as Nemotron placeholder
    # In production, this would call Nemotron via API
    score_adjustment = 0
    red_flags = []

    note_lower = request.note.lower()

    # Intent patterns
    if any(word in note_lower for word in ["urgent", "immediately", "asap", "hurry"]):
        score_adjustment += 10
        red_flags.append("urgency_pressure")

    if any(word in note_lower for word in ["verify", "confirm", "bank", "support", "kyc"]):
        score_adjustment += 15
        red_flags.append("impersonation_attempt")

    if any(word in note_lower for word in ["gift card", "crypto", "bitcoin", "voucher"]):
        score_adjustment += 12
        red_flags.append("irreversible_payout")

    # Clamp to ±15
    score_adjustment = max(-15, min(15, score_adjustment))

    return {
        "score_contribution": score_adjustment,
        "red_flags": red_flags,
        "model": "nemotron_heuristic",
    }


def generate_explanation(
    request: PaymentRequest,
    recipient_status: str,
    rule_score: float,
    fraud_flags: list,
    final_score: float,
) -> dict:
    """
    Use Claude for user-facing explanation (only for Medium/High risk or complex cases).
    Reserve Claude for explanation quality, not routine decisions.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "narrative": _build_default_explanation(rule_score, fraud_flags),
            "model": "default",
        }

    # Only call Claude for Medium/High risk (optimization)
    if final_score < 30:
        return {
            "narrative": _build_default_explanation(rule_score, fraud_flags),
            "model": "default",
        }

    client = Anthropic()

    flags_text = ", ".join(fraud_flags) if fraud_flags else "none detected"

    prompt = f"""You are a payment security expert. Provide a brief, clear explanation
for why we're asking the user to review this payment.

Payment Details:
- Recipient: {request.recipient_name} ({request.recipient_id})
- Amount: ${request.amount}
- Status: {recipient_status}
- Risk flags: {flags_text}
- Current score: {final_score:.0f}/100

In 1-2 sentences, explain the primary concern(s) in plain language suitable for a user.
Focus on the most actionable concern. Be direct but not alarmist."""

    try:
        message = client.messages.create(
            model="claude-sonnet-5",  # Use current Sonnet (not 3.5)
            max_tokens=150,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        narrative = message.content[0].text.strip()
        return {
            "narrative": narrative,
            "model": "claude-sonnet-5",
        }

    except Exception as e:
        return {
            "narrative": _build_default_explanation(rule_score, fraud_flags),
            "error": str(e),
            "model": "default_fallback",
        }


def _build_default_explanation(rule_score: float, fraud_flags: list) -> str:
    """
    Fallback explanation when Claude unavailable or for low-risk cases.
    """
    if not fraud_flags:
        return "Payment appears legitimate based on available information."

    explanations = {
        "urgency_pressure": "Urgent language detected in payment note.",
        "impersonation_attempt": "Language suggesting account verification or support request.",
        "irreversible_payout": "Request for payment via irreversible method (gift card, crypto).",
    }

    concerns = [explanations.get(flag, flag) for flag in fraud_flags]
    return " ".join(concerns)


def get_llm_reasoning(
    request: PaymentRequest,
    recipient_status: str,
    rule_score: float,
    final_score: float = None,
) -> dict:
    """
    Hybrid LLM reasoning: fast fraud classification + Claude explanations.

    Returns score adjustment and narrative explanation.
    """
    # Step 1: Fast fraud classification (Nemotron)
    fraud_result = classify_fraud_intent(request, recipient_status, rule_score)

    # Step 2: Generate explanation (Claude for Medium/High, default for Low)
    if final_score is None:
        final_score = rule_score + fraud_result["score_contribution"]

    explanation_result = generate_explanation(
        request,
        recipient_status,
        rule_score,
        fraud_result["red_flags"],
        final_score,
    )

    return {
        "score_contribution": fraud_result["score_contribution"],
        "narrative": explanation_result["narrative"],
        "fraud_model": fraud_result["model"],
        "explanation_model": explanation_result["model"],
    }
