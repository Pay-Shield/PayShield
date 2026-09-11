import os
import json
import re
import requests
from models import PaymentRequest


FLAG_TEXT = {
    "urgency_pressure": "Urgent language detected in payment note.",
    "threat_pressure": "Coercive language (account block, legal action, penalty) detected.",
    "impersonation_attempt": "Language suggesting account verification or support request.",
    "irreversible_payout": "Request for payment via irreversible method (gift card, crypto).",
}


def classify_fraud_intent(
    request: PaymentRequest,
    recipient_status: str,
    rule_score: float,
) -> dict:
    """
    Primary LLM classifier — Nemotron. Runs on every request. Returns a
    bounded score adjustment, detected red flags, and its own narrative
    (Nemotron generates the user-facing explanation directly; there's no
    separate explanation-only model in this build).
    Falls back to heuristics if the API is unavailable.
    """
    nemotron_key = os.getenv("NEMOTRON_API_KEY")

    if nemotron_key:
        print("    Attempting Nemotron API call...")
        result = _call_nemotron(request, recipient_status, rule_score)
        if result:
            print(f"    Nemotron returned: {result.get('red_flags', [])}")
            return result
        print("    Nemotron unavailable, falling back to heuristics")

    result = _classify_by_heuristics(request)
    print(f"    Using heuristics: {result.get('red_flags', [])}")
    return result


def _call_nemotron(
    request: PaymentRequest,
    recipient_status: str,
    rule_score: float,
) -> dict:
    """
    Call Nemotron 3.5 Lightning (NVIDIA NIM) for fraud intent classification
    AND its own narrative explanation.
    """
    api_key = os.getenv("NEMOTRON_API_KEY")
    api_endpoint = os.getenv(
        "NEMOTRON_API_ENDPOINT",
        "https://integrate.api.nvidia.com/v1/chat/completions"
    )
    model_id = os.getenv("NEMOTRON_MODEL_ID", "nvidia/nemotron-3.5-lightning-30b-a3b")

    prompt = f"""Analyze this payment request for fraud intent, social engineering, and impersonation.
Be concise and return ONLY valid JSON.

Payment:
- To: {request.recipient_name} ({request.recipient_id})
- Amount: ${request.amount}
- Status: {recipient_status}
- Note: "{request.note}"

Return JSON:
{{
    "score_adjustment": <integer -15 to 15>,
    "red_flags": [<list of strings: urgency_pressure, threat_pressure, impersonation_attempt, irreversible_payout, or none>],
    "concern": "<one plain-language sentence explaining the primary concern, or null if none>"
}}"""

    try:
        response = requests.post(
            api_endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id,
                # This Nemotron build is a reasoning model that emits chain-of-thought
                # before its answer unless told not to. "detailed thinking off" (the
                # documented toggle for the Nemotron reasoning family) alone didn't
                # suppress it in testing — chat_template_kwargs.thinking=false did.
                "messages": [
                    {"role": "system", "content": "detailed thinking off"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 1500,
                "chat_template_kwargs": {"thinking": False},
            },
            timeout=20,
        )

        if response.status_code != 200:
            print(f"    Nemotron API returned HTTP {response.status_code}: {response.text[:500]!r}")
            return None

        try:
            data = response.json()
        except ValueError:
            print(f"    Nemotron response body was not valid JSON. Raw body: {response.text[:500]!r}")
            return None

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            print(f"    Nemotron response had no message content. Full response: {json.dumps(data)[:500]}")
            return None

        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            print(f"    Nemotron response had no parseable JSON. Raw content: {content[:300]!r}")
            return None

        try:
            result = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            print(f"    Could not parse JSON from Nemotron content ({e}). Raw content: {content[:300]!r}")
            return None

        score_adjustment = max(-15, min(15, result.get("score_adjustment", 0)))
        red_flags = result.get("red_flags", [])
        concern = result.get("concern")
        narrative = concern if concern and concern != "null" else _build_default_explanation(red_flags)

        return {
            "score_contribution": score_adjustment,
            "red_flags": red_flags,
            "narrative": narrative,
            "model": model_id,
        }

    except Exception as e:
        print(f"    Nemotron request failed: {type(e).__name__}: {str(e)}")
        return None


def _classify_by_heuristics(request: PaymentRequest) -> dict:
    """
    Fallback heuristic fraud classification when the Nemotron API is
    unavailable (no key, or the call failed).

    Deliberately conservative weights: this heuristic re-detects largely the
    same keyword families the rule engine (modules.py) already scores, so it
    isn't an independent signal the way a real LLM call would be — giving it
    the full ±15 range would double-count and risk pushing scores past their
    intended category. A real model call is free to use more of the ±15
    range since its judgment is actually independent of the rules.
    """
    score_adjustment = 0
    red_flags = []

    combined_lower = f"{request.note} {request.recipient_name}".lower()
    note_lower = request.note.lower()

    if re.search(r"\burgent(ly)?\b|\bimmediate(ly)?\b|\basap\b|\bhurry\b|\btonight\b|\bexpir\w*\b", combined_lower):
        score_adjustment += 6
        red_flags.append("urgency_pressure")

    if re.search(r"\bblock(ed)?\b|\bdisconnect\w*\b|\bsuspend\w*\b|\barrest\w*\b|\bpolice\b|\bpenalty\b|\bfine\b", combined_lower):
        score_adjustment += 6
        red_flags.append("threat_pressure")

    if re.search(r"\bverify\b|\bconfirm\b|\bbank\b|\bsupport\b|\bkyc\b|\botp\b|\brefund\b", note_lower):
        score_adjustment += 10
        red_flags.append("impersonation_attempt")

    if re.search(r"gift\s*card|\bcrypto\b|\bbitcoin\b|\bvoucher\b|guaranteed.{0,20}return", note_lower):
        score_adjustment += 10
        red_flags.append("irreversible_payout")

    score_adjustment = max(-15, min(15, score_adjustment))

    return {
        "score_contribution": score_adjustment,
        "red_flags": red_flags,
        "narrative": _build_default_explanation(red_flags),
        "model": "heuristic_fallback",
    }


def _build_default_explanation(fraud_flags: list) -> str:
    if not fraud_flags:
        return "Payment appears legitimate based on available information."
    concerns = [FLAG_TEXT.get(flag, flag) for flag in fraud_flags]
    return " ".join(concerns)


def get_second_opinion(
    request: PaymentRequest,
    recipient_status: str,
    primary_red_flags: list,
    final_score: float,
) -> dict | None:
    """
    Independent second-model check (Gemini) — called only for Medium+ risk
    (final_score >= 30). Advisory only: it does NOT contribute to the score.
    The point is a genuine second opinion on cases that matter, not a second
    vote that could shift a decision the rules engine already made — "we
    don't rely on a single AI model," without re-touching the calibration
    that's already been verified against all 4 demo scenarios.

    Returns None if no GEMINI_API_KEY is set, if final_score < 30, or if the
    call fails — callers should treat None as "no second opinion available"
    and simply not show one, not as an error.
    """
    if final_score < 30:
        return None

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    print("    Requesting Gemini second opinion (elevated risk)...")
    result = _call_gemini(request, recipient_status, primary_red_flags, final_score)
    if result:
        print(f"    Gemini second opinion: {'agrees' if result['agrees'] else 'disagrees'} — {result['assessment'][:80]!r}")
    else:
        print("    Gemini second opinion unavailable")
    return result


def _call_gemini(
    request: PaymentRequest,
    recipient_status: str,
    primary_red_flags: list,
    final_score: float,
) -> dict | None:
    api_key = os.getenv("GEMINI_API_KEY")
    model_id = os.getenv("GEMINI_MODEL_ID", "gemini-2.0-flash")
    api_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"

    flags_text = ", ".join(primary_red_flags) if primary_red_flags else "none"

    prompt = f"""You are an independent second reviewer for a payment security system. Another model
already flagged this payment as elevated risk (score {final_score:.0f}/100) with these concerns: {flags_text}.
Give your own independent read — do not just agree by default.

Payment:
- To: {request.recipient_name} ({request.recipient_id})
- Amount: ${request.amount}
- Recipient status: {recipient_status}
- Note: "{request.note}"

Return ONLY this JSON:
{{
    "agrees_with_primary_assessment": <true or false>,
    "assessment": "<one sentence, your independent take>"
}}"""

    try:
        response = requests.post(
            f"{api_endpoint}?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 300},
            },
            timeout=20,
        )

        if response.status_code != 200:
            print(f"    Gemini API returned HTTP {response.status_code}: {response.text[:500]!r}")
            return None

        data = response.json()
        content = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if not content:
            print(f"    Gemini response had no content. Full response: {json.dumps(data)[:500]}")
            return None

        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            print(f"    Gemini response had no parseable JSON. Raw content: {content[:300]!r}")
            return None

        result = json.loads(json_match.group())
        return {
            "agrees": bool(result.get("agrees_with_primary_assessment", True)),
            "assessment": result.get("assessment", ""),
            "model": model_id,
        }

    except Exception as e:
        print(f"    Gemini request failed: {type(e).__name__}: {str(e)}")
        return None


def get_llm_reasoning(
    request: PaymentRequest,
    recipient_status: str,
    rule_score: float,
    final_score: float = None,
) -> dict:
    """
    Nemotron (primary, always runs) classifies + explains. Gemini (secondary,
    advisory only) is consulted for elevated-risk cases as an independent
    check — it never alters the score. Deterministic rules remain the final
    policy layer regardless of what either model says.
    """
    fraud_result = classify_fraud_intent(request, recipient_status, rule_score)

    if final_score is None:
        final_score = rule_score + fraud_result["score_contribution"]

    narrative = fraud_result["narrative"]
    second_opinion = get_second_opinion(
        request, recipient_status, fraud_result["red_flags"], final_score
    )
    if second_opinion:
        agreement = "confirms this assessment" if second_opinion["agrees"] else "flags a different concern"
        narrative = f"{narrative} Independent cross-check {agreement}: {second_opinion['assessment']}"

    return {
        "score_contribution": fraud_result["score_contribution"],
        "red_flags": fraud_result["red_flags"],
        "narrative": narrative,
        "fraud_model": fraud_result["model"],
        "second_opinion_model": second_opinion["model"] if second_opinion else None,
    }
