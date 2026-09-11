# PayShield — Progress Tracker

Reference spec: `guardian-architecture.md`. This file tracks what's actually built and verified, vs. what's written but untested, vs. what's missing — updated as work continues.

Last verified: 2026-09-11 (backend started locally, hit with curl, frontend built with `npm run build` + `tsc --noEmit`).

---

## Honest status: where we really are

**The good news:** the core risk pipeline works. Rules + Nemotron/heuristic fallback + Claude/template fallback + aggregation + audit log are real, running code, not just scaffolding — verified by actually calling the endpoints, not just reading them.

**The gap:** the architecture doc's step 4 (**HUMAN-IN-THE-LOOP CHECKPOINT** — "skipped only for Low") is not enforced in the React frontend flow. The Payment Simulator shows the risk result and lets the user click "Continue" regardless of category — it does not require an explicit confirm/cancel decision before the transaction is recorded as done for Medium/High risk. That checkpoint **does** exist in the original PS09-native `/api/confirm` endpoint, it's just not wired into the UI that's actually being demoed. This is the single biggest thing standing between "looks done" and "is done" — see Phase 5 below.

**Also found while testing today (not previously known):** one of the four required demo scenarios misfires. See "Bugs found" below.

---

## Build scope checklist (guardian-architecture.md §9)

| In scope | Status |
|---|---|
| Simulated payment request form/API | ✅ Done — form in React Payment Simulator + `/api/transactions/analyze` |
| Five internal modules, parallelized where independent | ⚠️ Built and running in parallel (`asyncio.gather`), but 2 of 5 are thinner than the spec implies — see below |
| Rule engine + one real LLM call for reasoning/explanation | ⚠️ Code path exists and is hybrid (Nemotron classify + Claude explain per [[hybrid_llm_approach]] decision); **neither has been called with a real API key yet** — everything tested so far ran on the heuristic/template fallback |
| Aggregation and category mapping | ✅ Done, verified correct on 3/4 demo scenarios |
| Human confirmation UI step | ❌ **Missing in the live frontend.** Exists only in the unused PS09-native flow |
| Persistent audit log | ✅ Done — JSONL, verified entries written on real requests |
| Four demo scenarios wired up | ⚠️ 3/4 verified correct against the real backend; 1 misclassified (Scenario 3) |

| Explicitly out of scope (per spec — correctly not built) | Status |
|---|---|
| Real/live payment gateway | ✅ correctly absent |
| Hash-chained/tamper-proof audit log | ✅ correctly absent |
| Vector DB / RAG scam patterns | ✅ correctly absent |
| Multi-agent orchestration framework | ✅ correctly absent (plain async functions, as intended) |
| Post-completion flows (reversal, dispute, monitoring) | ✅ correctly absent |

---

## Module-by-module reality check (architecture §3)

| Module | Spec says | What's actually built |
|---|---|---|
| **Recipient Verification** | known/new/flagged, account age, ID format check | Hardcoded 5-entry dict (`GOOG`, `AMZN`, `UTIL` known; `SCAM001`, `FRAUD_NET` flagged). **Bug:** format regex `^[A-Z0-9]{3,}$` rejects UPI-style ids (`name@bank`) that the frontend actually sends — every UPI handle gets flagged `invalid_format` (+20) instead of being read as a normal new recipient. Not connected to the frontend's separate mock recipient list either. |
| **Risk Analysis (rules)** | amount vs baseline, keyword hits (urgency/impersonation/gift-card) | Amount check works correctly. **Bug:** keyword matching does exact whole-word set-intersection on `note.split()` — "immediate" ≠ "immediately", punctuation isn't stripped, and only the `note` field is scanned (not recipient name/id, which is where scam signal often lives, e.g. "Electricity Billing Cell"). This is why Scenario 3 misfires. |
| **Behavioral Pattern** | velocity — 2+ new-recipient attempts in a session, amount deviation from own history | **Stub.** Function exists and is called, but nothing ever passes it real session history — `behavioral_score` is always 0 in every test run so far. No session store, no per-user baseline. |
| **LLM Reasoning** | Reads note, judges intent, contributes score + narrative | Hybrid path is coded (Nemotron classify → Claude explain, [[hybrid_llm_approach]]), but **only the fallback paths have been exercised**: keyword heuristic (no `NEMOTRON_API_KEY` set) and default template text (Claude only fires for Medium+/High risk and hasn't been hit with a real key in this session's tests). |
| **Decision & Policy** | combine signals → 0-100 score → category → action | ✅ Working as designed, correct thresholds, correctly capped at 100. |

---

## Bugs found today (verified, not hypothetical)

1. **Scenario 3 ("Utility Threat Scam") misclassifies as WARNING/VERIFY instead of HIGH/PAUSED.**
   Input: `{recipientName: "Electricity Billing Cell", upiId: "urgent.power@upi", amount: 25000, message: "Immediate payment or power disconnect tonight"}`
   Got: `risk_score: 50, risk_level: WARNING, action: VERIFY`
   Expected (per architecture §8, demo scenario "Suspicious request"): High risk, re-verify + confirm.
   Root cause: urgency keyword list doesn't match "Immediate" (only "immediately" is listed) and there's no "threat" keyword category (block/disconnect/suspend) in the backend rule engine at all — the frontend's own client-side fallback simulator has this detection, the Python backend doesn't.

2. **UPI-style recipient IDs always fail format validation**, inflating `recipientRisk` and producing a confusing `invalid_format` status for completely normal-looking recipients like `rahul@upi`. Doesn't currently flip any demo scenario's top-line category, but it's wrong and will look wrong if graders inspect the reasons/breakdown.

3. **Reason-list noise:** the generic fallback line "Payment appears legitimate based on available information." can appear in the `reasons` array *alongside* real risk factors (e.g. Scenario 3's response had it right next to "Transfer amount is more than 5x baseline"), which reads as self-contradictory in the UI.

None of these are hard to fix — they're all in `backend/modules.py` (keyword lists + regex) and `backend/frontend_adapter.py`/`llm_reasoning.py` (reason-list de-duplication) — but they were not caught until today's verification pass, so flagging them plainly rather than letting the earlier "all tests passing" summary stand uncorrected.

---

## Phases

### ✅ Phase 1 — Setup & Core Infrastructure
FastAPI backend, Pydantic models, five-module skeleton, JSONL audit log, initial plain HTML/JS UI (now archived).

### ✅ Phase 2 — Hybrid LLM Architecture
Switched from "Claude for every call" to Nemotron (fast classification) + Claude (explanations, Medium/High only) + rules-as-final-authority, per [[hybrid_llm_approach]].

### ✅ Phase 3 — API Bug Fixes
Fixed the original 422 on `/api/confirm`, enum serialization, CORS, logging. Verified via `test_api.py` (PS09-native contract only).

### ✅ Phase 4 — Frontend Integration
Adopted the provided React/TS/Vite app in place of the plain HTML/JS UI (archived, not deleted, to `archived/`). Built `pipeline.py` (shared core) + `frontend_adapter.py` (contract translation) so both the PS09-native and React-frontend contracts run the identical pipeline. Verified today: `tsc --noEmit` clean, `npm run build` succeeds, `/api/transactions/analyze` and `/api/security/scam-check` both respond correctly end-to-end against a running backend.

### 🔴 Phase 5 — Close the gaps (next, before submission)
In priority order:

1. **Wire the human-in-the-loop checkpoint into the actual React flow.** Medium (VERIFY) and High (PAUSED) must require an explicit user confirm/cancel — not just display-and-continue — before the transaction is logged as `completed`. This is the architecture's core safety claim (§2, §4, §6); right now it's not demoable because it doesn't exist in the UI actually being shown.
2. **Fix the rule-engine keyword matching** (substring/regex instead of exact-word set intersection; add a "threat" category; optionally scan recipient name too) so Scenario 3 correctly lands on HIGH/PAUSED.
3. **Fix recipient ID format validation** to accept UPI-style handles instead of flagging them all as `invalid_format`.
4. **Wire real session/behavioral tracking** — even a simple in-memory per-`sender_id` list of recent recipient attempts would make the Behavioral Pattern module non-stub and match §3/§5's velocity requirement.
5. **Clean up reason-list contradiction** — don't emit the generic "appears legitimate" line when real risk factors are present.
6. **Actually exercise the real Nemotron and Claude API paths** with live keys at least once each, and note in this file whether they behaved as expected (score adjustment, latency, JSON parsing robustness) — everything verified so far has been the fallback path.
7. **Full 4-scenario browser run**: both servers up, all four Payment Simulator presets clicked through in the actual UI, screenshots or a short note confirming each lands on the right category/action, audit log inspected afterward for all four.
8. **Reconcile or document** the disconnect between the backend's hardcoded recipient dict and the frontend's separate `mockData.ts` recipient list (different data, same concept) — at minimum note it as a known seam in the README; ideally have the simulator's presets match recipients the backend actually recognizes as known.

### ⚪ Phase 6 — Submission polish (after Phase 5)
- Re-run `test_api.py` and add equivalent smoke tests for `/api/transactions/analyze` and `/api/security/scam-check`
- Skim `README.md` against whatever Phase 5 actually changes and correct any drift
- Confirm `.env.example` keys are accurate and nothing secret is committed
- One clean end-to-end dry run of the exact demo you intend to give

---

## Quick reference: what "done" currently means

Verified working right now, if you run it: submit a payment through the React Payment Simulator (backend + frontend both running) → real rules + fallback LLM reasoning run → risk score/category/action computed → shown in the UI → written to `audit_log.jsonl`. That loop is real. What's not yet real: the loop stopping to ask "do you want to proceed?" on risky payments, one of the four required demo cases landing on the right severity, and the LLM steps having been checked against actual Nemotron/Claude responses rather than their fallbacks.
