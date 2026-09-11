from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from models import PaymentRequest, UserConfirmation, RiskAnalysisResult
from modules import recipient_verification, risk_analysis_rules, behavioral_pattern
from llm_reasoning import get_llm_reasoning
from aggregator import aggregate_and_decide, format_explanation
from audit_log import log_transaction, get_audit_history
import os

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (HTML, TypeScript, etc.)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.post("/api/analyze")
async def analyze_payment(request: PaymentRequest):
    """
    Main endpoint: analyze payment through all modules.
    Returns risk score, category, action, and explanation.
    """
    try:
        print(f"\n📊 Analyzing payment: {request.recipient_name} for ${request.amount}")

        # Run modules in parallel where possible
        recipient_result, rule_result, behavioral_result = await asyncio.gather(
            asyncio.to_thread(recipient_verification, request),
            asyncio.to_thread(risk_analysis_rules, request),
            asyncio.to_thread(behavioral_pattern, request),
        )

        print(f"  ✓ Recipient: {recipient_result.get('status')}")
        print(f"  ✓ Rules: {rule_result['score']:.0f}")
        print(f"  ✓ Behavioral: {behavioral_result['score']:.0f}")

        # Get LLM reasoning (can also run in parallel)
        # Pre-calculate tentative score for LLM to decide if Claude explanation is needed
        tentative_score = (
            recipient_result.get("score_contribution", 0) +
            rule_result["score"] +
            behavioral_result["score"]
        )

        print(f"  🤖 Calling LLM for fraud classification...")
        llm_result = await asyncio.to_thread(
            get_llm_reasoning,
            request,
            recipient_result.get("status", "unknown"),
            rule_result["score"],
            tentative_score,
        )
        print(f"  ✓ LLM Model: {llm_result.get('fraud_model', 'unknown')}")
        print(f"  ✓ LLM Adjustment: {llm_result.get('score_contribution', 0)}")

        # Aggregate all scores
        decision = aggregate_and_decide(
            recipient_score=recipient_result.get("score_contribution", 0),
            rule_score=rule_result["score"],
            behavioral_score=behavioral_result["score"],
            llm_adjustment=llm_result.get("score_contribution", 0),
        )

        print(f"  📈 Final Score: {decision['final_score']:.0f}")
        print(f"  🎯 Category: {decision['category']}")
        print(f"  ⚡ Action: {decision['action']}")

        # Combine all factors
        all_factors = (
            rule_result.get("factors", []) +
            behavioral_result.get("factors", []) +
            [{"type": "llm_red_flags", "flags": llm_result.get("red_flags", [])}]
        )

        # Format explanation
        explanation = format_explanation(
            category=decision["category"],
            final_score=decision["final_score"],
            factors=all_factors,
            llm_narrative=llm_result.get("narrative", ""),
        )

        return RiskAnalysisResult(
            risk_score=decision["final_score"],
            category=decision["category"],
            action=decision["action"],
            factors=all_factors,
            llm_reasoning=explanation,
            confidence=0.85,
        )

    except Exception as e:
        print(f"❌ Error in analyze_payment: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@app.post("/api/confirm")
async def confirm_payment(
    body: dict = Body(...)
):
    """
    Handle user confirmation/cancellation.
    Expects: {"request": PaymentRequest, "confirmed": bool}
    """
    try:
        request_data = body.get("request")
        confirmed = body.get("confirmed", False)

        if not request_data:
            raise HTTPException(status_code=400, detail="Missing payment request data")

        # Reconstruct PaymentRequest object
        request = PaymentRequest(**request_data)

        if confirmed:
            # Re-run analysis to get final decision
            analysis = await analyze_payment(request)

            if analysis.category.lower() in ["low", "medium", "high"]:
                # Allowed to proceed
                outcome = "completed"
            else:
                # CRITICAL: cannot proceed
                outcome = "blocked"
                log_transaction(
                    request=request,
                    recipient_verification={},
                    risk_factors=analysis.factors,
                    llm_reasoning=analysis.llm_reasoning,
                    final_score=analysis.risk_score,
                    category=analysis.category,
                    action=analysis.action,
                    outcome=outcome,
                )
                raise HTTPException(status_code=403, detail="Payment blocked: too high risk.")

            # Log to audit
            log_transaction(
                request=request,
                recipient_verification={},
                risk_factors=analysis.factors,
                llm_reasoning=analysis.llm_reasoning,
                final_score=analysis.risk_score,
                category=analysis.category,
                action=analysis.action,
                outcome=outcome,
            )

            return {"status": "completed", "message": "Payment processed successfully."}
        else:
            # User cancelled
            log_transaction(
                request=request,
                recipient_verification={},
                risk_factors=[],
                llm_reasoning="",
                final_score=0,
                category="cancelled",
                action="user_cancelled",
                outcome="cancelled",
            )
            return {"status": "cancelled", "message": "Payment cancelled by user."}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in confirm_payment: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error processing confirmation: {str(e)}")


@app.get("/api/audit-history")
async def get_history(limit: int = 50):
    """
    Retrieve audit log history.
    """
    return get_audit_history(limit)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
