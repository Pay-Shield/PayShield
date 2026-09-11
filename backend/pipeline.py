import asyncio
from models import PaymentRequest
from modules import recipient_verification, risk_analysis_rules, behavioral_pattern
from llm_reasoning import get_llm_reasoning
from aggregator import aggregate_and_decide, format_explanation
from session_store import get_recent_attempts, record_attempt


async def run_risk_pipeline(request: PaymentRequest) -> dict:
    """
    Core PayShield pipeline, shared by every endpoint that needs a risk decision.

    Runs Recipient Verification, Risk Rules, and Behavioral Pattern in parallel,
    then LLM Reasoning (Nemotron classify + Claude explain), then aggregates.
    """
    print(f"\n📊 Analyzing payment: {request.recipient_name} for ${request.amount}")

    session_history = get_recent_attempts(request.sender_id)

    recipient_result, rule_result, behavioral_result = await asyncio.gather(
        asyncio.to_thread(recipient_verification, request),
        asyncio.to_thread(risk_analysis_rules, request),
        asyncio.to_thread(behavioral_pattern, request, session_history),
    )

    # Record this attempt AFTER computing velocity so it doesn't count itself
    record_attempt(request.sender_id, request.recipient_id, recipient_result.get("status", "new"))

    print(f"  ✓ Recipient: {recipient_result.get('status')}")
    print(f"  ✓ Rules: {rule_result['score']:.0f}")
    print(f"  ✓ Behavioral: {behavioral_result['score']:.0f} (session has {len(session_history)} prior attempt(s))")

    tentative_score = (
        recipient_result.get("score_contribution", 0) +
        rule_result["score"] +
        behavioral_result["score"]
    )

    print("  🤖 Calling LLM for fraud classification...")
    llm_result = await asyncio.to_thread(
        get_llm_reasoning,
        request,
        recipient_result.get("status", "unknown"),
        rule_result["score"],
        tentative_score,
    )
    print(f"  ✓ LLM Model: {llm_result.get('fraud_model', 'unknown')}")
    print(f"  ✓ LLM Adjustment: {llm_result.get('score_contribution', 0)}")

    decision = aggregate_and_decide(
        recipient_score=recipient_result.get("score_contribution", 0),
        rule_score=rule_result["score"],
        behavioral_score=behavioral_result["score"],
        llm_adjustment=llm_result.get("score_contribution", 0),
    )

    print(f"  📈 Final Score: {decision['final_score']:.0f}")
    print(f"  🎯 Category: {decision['category']}")
    print(f"  ⚡ Action: {decision['action']}")

    all_factors = (
        rule_result.get("factors", []) +
        behavioral_result.get("factors", []) +
        [{"type": "llm_red_flags", "flags": llm_result.get("red_flags", [])}]
    )

    explanation = format_explanation(
        category=decision["category"],
        final_score=decision["final_score"],
        factors=all_factors,
        llm_narrative=llm_result.get("narrative", ""),
    )

    return {
        "recipient_result": recipient_result,
        "rule_result": rule_result,
        "behavioral_result": behavioral_result,
        "llm_result": llm_result,
        "decision": decision,
        "all_factors": all_factors,
        "explanation": explanation,
    }
