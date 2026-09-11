# PayShield Guardian - Agentic Payment Security

Intelligent payment security assistant that analyzes payment requests through multiple specialist modules, produces risk scores, and makes secure decisions with human-in-the-loop oversight.

## Architecture

**Five Internal Modules (not multi-agent):**
1. **Recipient Verification** — Is the payee known, new, or flagged?
2. **Risk Analysis (Rules)** — Amount, keywords, urgency/impersonation language
3. **Behavioral Pattern** — Velocity checks and user baseline deviation
4. **LLM Reasoning (Hybrid)** — Nemotron for fast fraud classification; Claude for user-facing explanations (Medium/High risk only)
5. **Decision & Policy** — Aggregates all signals → score → category → action

**Key Principle:** Rules + LLM support the decision; deterministic rules engine is the final authority. No LLM-only decisions.

**Model Stack:**
- **Fraud Classification:** Nemotron 3.5 Lightning (fast, lightweight)
- **Explanations:** Claude Sonnet 5 (high-quality, reserved for Medium/High risk)
- **Fallback:** Heuristic rules if APIs unavailable

**Categories:**
- **Low (<30)** → Auto-approve
- **Medium (30–59)** → Require confirmation
- **High (60–84)** → Require verification + confirmation
- **Critical (85+)** → Hard block, no override

## Setup

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
```

Edit `.env` with your API keys:
```
ANTHROPIC_API_KEY=sk-...  # Claude API key (for explanations)
NEMOTRON_API_KEY=...       # Nemotron API key (for fraud classification)
NEMOTRON_API_ENDPOINT=...  # Optional, defaults to NVIDIA API Catalog
```

**Note:** 
- If `NEMOTRON_API_KEY` is missing, fraud classification falls back to heuristics
- If `ANTHROPIC_API_KEY` is missing, explanations use default templates
- Both are optional but recommended for full functionality

### 3. Run the server
```bash
python backend/main.py
```

The application will start at `http://localhost:8000`

## Project Structure

```
payshield/
├── backend/
│   ├── main.py              # FastAPI app, endpoints
│   ├── models.py            # Pydantic data models
│   ├── modules.py           # Five core analysis modules
│   ├── llm_reasoning.py     # Claude API integration
│   ├── aggregator.py        # Decision logic & explanation
│   └── audit_log.py         # Transaction logging
├── static/
│   ├── index.html           # Main UI
│   ├── styles.css           # Styling
│   └── app.js               # Frontend logic
├── requirements.txt         # Python dependencies
├── .env.example             # Environment template
└── guardian-architecture.md # Full architecture spec
```

## API Endpoints

### `POST /api/analyze`
Analyze a payment request through all modules.

**Request:**
```json
{
  "sender_id": "USER123",
  "recipient_name": "John Doe",
  "recipient_id": "JOHN001",
  "amount": 500.00,
  "note": "Payment for services"
}
```

**Response:**
```json
{
  "risk_score": 35,
  "category": "medium",
  "action": "require_confirmation",
  "factors": [...],
  "llm_reasoning": "...",
  "confidence": 0.85
}
```

### `POST /api/confirm`
Handle user confirmation or cancellation.

**Request:**
```json
{
  "request": {...},
  "confirmed": true
}
```

**Response:**
```json
{
  "status": "completed",
  "message": "Payment processed."
}
```

### `GET /api/audit-history`
Retrieve recent transaction audit log.

**Response:**
```json
[
  {
    "timestamp": "2025-09-11T...",
    "request": {...},
    "final_score": 35,
    "category": "medium",
    "outcome": "completed"
  }
]
```

## Demo Scenarios

The application is pre-configured to handle these cases:

1. **Normal Payment** (Auto-approve)
   - Recipient: GOOG (known)
   - Amount: 100 (typical)
   - Note: Plain language
   - Expected: Low risk, auto-proceed

2. **New Recipient** (Require confirmation)
   - Recipient: NEW_RECIPIENT_001
   - Amount: 150
   - Note: Plain language
   - Expected: Medium risk, confirm

3. **Suspicious Request** (Require verification)
   - Recipient: UNKNOWN_ID
   - Amount: 5000 (5x baseline)
   - Note: "Urgent: refund needed immediately"
   - Expected: High risk, verify + confirm

4. **High-Risk Block**
   - Recipient: SCAM001 (flagged)
   - Amount: 10000 (far above baseline)
   - Note: "Urgent gift card purchase required immediately"
   - Expected: Critical risk, hard block

## Testing

Visit `http://localhost:8000` and submit different payment scenarios to see:
- Risk scoring in action
- LLM reasoning explanations
- Human-in-the-loop decision points
- Audit log persistence

## Architecture Philosophy

- **Single agent, modular internals** — avoids orchestration overhead
- **Deterministic rules + LLM support** — Rules are the final authority. LLM provides fraud classification (fast) + explanations (high-quality)
- **Intelligent LLM usage** — Nemotron (lightweight) for routine fraud detection; Claude (expensive) reserved for user-facing explanations and edge cases
- **Parallel execution** — independent modules run concurrently
- **Human-in-the-loop by design** — medium/high risk require explicit user confirmation
- **Simulated payments** — no real gateway integration
- **Persistent audit log** — JSONL format for transparency

**Why this hybrid approach?**

```
Payment Request
      ↓
Rule Engine (deterministic)
      ↓
Nemotron (fast fraud classification)
      ↓
Risk Score (rule-based with LLM input)
  ┌───┼────┐
 LOW MEDIUM HIGH
 ↓     ↓     ↓
Allow  Review Claude
             ↓
        User Explanation
```

- Rules ensure consistency and auditability
- Nemotron handles fast, routine fraud detection
- Claude provides high-quality explanations for cases needing human review
- No single LLM decides financial transactions alone

See `guardian-architecture.md` for complete technical specification.
