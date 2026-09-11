import os
from anthropic import Anthropic
from models import PaymentRequest


def get_llm_reasoning(
    request: PaymentRequest,
    recipient_status: str,
    rule_score: float,
) -> dict:
    """
    Call Claude to assess intent from the note, produce risk contribution and narrative.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "error": "ANTHROPIC_API_KEY not set",
            "score_contribution": 0,
            "narrative": "LLM reasoning unavailable.",
        }

    client = Anthropic()

    prompt = f"""You are a payment security expert. Analyze this payment request for social engineering,
impersonation, and intent manipulation. Be concise.

Payment Details:
- To: {request.recipient_name} ({request.recipient_id})
- Amount: ${request.amount}
- Recipient status: {recipient_status} (known/new/flagged)
- Current rule-based score: {rule_score}/100
- User note: "{request.note}"

Provide:
1. A risk score adjustment (-15 to +15) based on the note's language and intent
2. A one-sentence plain-language explanation of the primary concern (if any)

Format your response as JSON:
{{
    "score_adjustment": <number>,
    "concern": "<one sentence or null if low concern>"
}}"""

    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        response_text = message.content[0].text
        # Parse JSON from response
        import json
        import re
        json_match = re.search(r"\{[^}]+\}", response_text)
        if json_match:
            result = json.loads(json_match.group())
            return {
                "score_contribution": result.get("score_adjustment", 0),
                "narrative": result.get("concern", "No specific concern noted."),
                "raw_response": response_text,
            }
        else:
            return {
                "score_contribution": 0,
                "narrative": "Could not parse LLM response.",
                "raw_response": response_text,
            }

    except Exception as e:
        return {
            "error": str(e),
            "score_contribution": 0,
            "narrative": f"LLM error: {str(e)}",
        }
