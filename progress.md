# PayShield — Progress Tracker

Reference spec: `guardian-architecture.md`. This file tracks what's actually built and verified, vs. what's written but untested, vs. what's missing — updated as work continues.

Last verified: 2026-09-11 (Phase 5 pass — see below). All claims in this file are backed by an actual curl/tsc/build run in this session, not just code review.

---

## Honest status: where we really are now

**Phase 5 (close the gaps) is done.** All four demo scenarios now land on the correct category/action against the real backend, verified in the natural click-through order (not cherry-picked isolated calls). The human-in-the-loop checkpoint is now real and enforced in the React UI, not just the unused PS09-native flow. Three previously-unknown bugs surfaced *during this fix pass* (not in the original audit) and were fixed too — listed below so nothing gets quietly lost.

**Update — real Nemotron is now live and verified.** User added a real `NEMOTRON_API_KEY` (from build.nvidia.com/NIM) and asked to get it actually working. Found and fixed a chain of real bugs to get there — see "Nemotron: from key-added to actually working" below. All 4 demo scenarios re-verified with the live model in the loop. Claude explanation path is still the one thing not yet exercised with a real key (user's call — doing it later). Dashboard/transaction-list status doesn't yet re-sync after a confirm/cancel decision (cosmetic — the audit log and risk decision are correct either way).

---

## Fixes applied this session

### 1. Human-in-the-loop checkpoint — now real (was: missing)
- New backend endpoint `POST /api/transactions/confirm` (`backend/main.py`) resolves a pending VERIFY/PAUSED decision. Critical/BLOCKED always rejects with 403 regardless of input — no override path exists, by design.
- New `backend/pending_store.py` — in-memory store keyed by `transaction_id`, written by `/api/transactions/analyze` for any non-SAFE action, popped by `/api/transactions/confirm`.
- `frontend/src/services/api.ts` — `analyzePayment` now returns `{data, viaBackend}` so the UI knows whether there's a real pending decision to resolve or (fallback mode) nothing to call. Added `confirmTransaction()`.
- `frontend/src/components/simulator/PaymentSimulatorModal.tsx` — VERIFY now shows a **Confirm & Proceed / Cancel Payment** step that must be resolved; PAUSED additionally requires a **Simulate OTP Verification** click first (simulated identity re-check, per architecture §6). The "Continue" / "View Investigation" footer buttons are hidden until the decision resolves — a risky payment can no longer be waved through by just closing the modal.
- Verified: full confirm happy-path tested via curl, audit log shows the two-line trail (`pending_confirmation` → `completed`) correctly. Verified confirming a since-resolved transaction 404s. Verified attempting to confirm a BLOCKED transaction 403s with "no override available."

### 2. Rule-engine keyword matching — rewritten (was: exact whole-word set match, missed "immediate" vs "immediately", no threat category)
- `backend/modules.py` — replaced set-intersection with regex (`URGENCY_RE`, `THREAT_RE`, `IMPERSONATION_RE`, `GIFT_CARD_RE`), added a `threat_language`/`coercive_pressure` category that didn't exist before.
- Same fix mirrored in `backend/llm_reasoning.py`'s heuristic fallback classifier (it had the identical bug, just via substring instead of set-intersection).
- **Bug found while fixing this**: scanning the recipient *name* for impersonation keywords caused a legitimate-looking name like "Electricity Billing Cell" to self-trigger `impersonation_language` (+25) on the word "electricity" — double-counting with the threat signal and forcing every utility-style scenario into Critical regardless of actual content. Fixed by scoping urgency/threat detection to note+recipient-name (scam handles do legitimately embed urgency, e.g. `urgent.power@upi`) but impersonation/gift-card detection to the note only (a real payee's own name shouldn't be able to accuse itself).

### 3. Recipient ID validation + known/flagged lists — reconciled with frontend
- `backend/modules.py` — format regex now accepts UPI-style VPAs (`name@bank`) as well as legacy bank-code IDs; previously every UPI handle the frontend actually sends was wrongly flagged `invalid_format`.
- `KNOWN_RECIPIENTS` / `FLAGGED_RECIPIENTS` now include the exact UPI IDs the frontend's Payment Simulator presets and `mockData.ts` use (`rahul@upi`, `merchant@upi`, `aakash.v@axisbank`, `zomato@hdfcbank` as known; `invest-guaranteed@okhdfcbank` as flagged), reconciling the two previously-disconnected recipient datasets **for the four demo scenarios specifically**. The rest of `mockData.ts`'s dashboard data (unrelated mock transactions/recipients not touched by the simulator) is still a separate cosmetic dataset — noted as a known remaining seam, not a blocker.

### 4. Behavioral Pattern module — now real (was: permanent stub, always scored 0)
- New `backend/session_store.py` — in-memory, per-`sender_id`, 30-minute rolling window of recent payment attempts.
- `backend/pipeline.py` — fetches session history before the parallel module fan-out, records the current attempt after recipient verification resolves (so it doesn't count itself).
- Verified: running scenario 2 then scenario 3 back-to-back correctly shows velocity contributing once a sender has 2+ new/flagged-recipient attempts in the window — confirmed both in isolation (no velocity) and accumulated (velocity fires) via repeated curl calls.

### 5. Reason-list contradiction — fixed
- `backend/frontend_adapter.py` `build_reasons()` no longer appends the generic "Payment appears legitimate based on available information." line when real risk factors are already present in the list.

### 6. Two bugs found *while fixing the above*, not on the original list
- **`get_llm_reasoning()` never returned `red_flags`** in its result dict (`backend/llm_reasoning.py`) — silently empty on every single call since it was written. `pipeline.py`'s `llm_red_flags` factor and `frontend_adapter.py`'s `socialEngineeringRisk` bonus were reading nothing. Fixed by adding the key to the return dict. Confirmed via the aggregate score is unaffected (red_flags only fed display/breakdown, not the actual score path) — re-ran all 4 scenarios after the fix, all still correct.
- **Emoji in `print()` crashed every request with `UnicodeEncodeError`** the moment output was redirected on this Windows machine (cp1252 console codepage can't encode `📊`/`❌`/etc.). This wasn't a cosmetic issue — it took down `/api/transactions/analyze` with a 500 on literally every call once discovered. Fixed by reconfiguring `sys.stdout`/`sys.stderr` to UTF-8 at the top of `backend/main.py` rather than stripping emoji (keeps logs scannable, fixes it for any future log line too). Also discovered the earlier "reasons text looks garbled" scare during this session was a red herring — verified the actual `audit_log.jsonl` bytes directly with the Read tool and the JSON is correctly UTF-8 escaped (`•`, `❌`); the garbling was a `curl | python -m json.tool` pipe-through-Git-Bash display artifact only, not real data corruption.

---

## Nemotron: from key-added to actually working

The user added a real `NEMOTRON_API_KEY` and asked to verify it. It didn't work on the first several attempts — each failure was a distinct, real bug, fixed in sequence:

1. **`.env` was never actually loaded.** `python-dotenv` was in `requirements.txt` but `load_dotenv()` was never called anywhere in the codebase — meaning no API key from `.env` has ever reached any process this entire project, silently, since Phase 1. First request with the "configured" key still hit the fallback with zero attempt at a real call. Fixed: `load_dotenv()` added at the top of `backend/main.py`.
2. **The endpoint URL was wrong.** `https://api.nemo.nvidia.com/v1/chat/completions` — flagged in this file earlier as a guessed/unverified placeholder, confirmed wrong (plain-text `404 page not found`). Fixed to NVIDIA's real API Catalog endpoint: `https://integrate.api.nvidia.com/v1/chat/completions`.
3. **The model ID needed an `nvidia/` org prefix.** Updated to `nvidia/nemotron-3.5-lightning-30b-a3b`, now configurable via a new `NEMOTRON_MODEL_ID` env var.
4. **This Nemotron build is a reasoning model** — it emits extended chain-of-thought ("Here's a thinking process: 1. Analyze User Input...") before its actual answer. At `max_tokens=200` it got cut off mid-thought, never reaching the JSON. Bumping `max_tokens` alone just meant a longer wait before either truncation or a timeout (one attempt hit a 45s read-timeout with `max_tokens=1500` and thinking still not suppressed).
5. **Fix:** added `"chat_template_kwargs": {"thinking": False}` to the request payload (the standard NIM control for this) alongside a `"detailed thinking off"` system message (which alone hadn't been sufficient). That fixed it — the model now returns a fast, clean JSON answer.

Also hardened `_call_nemotron`'s error handling while debugging this (separate try/except around the HTTP call, the response-body JSON parse, and the content-JSON-extraction parse, each printing exactly what failed) — worth keeping regardless of the specific bug, since the original single broad `except Exception` gave no way to tell "wrong URL" from "malformed JSON" from "timeout" apart, which is exactly what made this take several iterations instead of one.

**Verified working, 4/4 scenarios, live model in the loop** (not the fallback):
| # | Scenario | Result | Latency | Nemotron red_flags returned |
|---|---|---|---|---|
| 1 | Trusted Friend | SAFE / SAFE / score 5 | 1.95s | `['none']` |
| 2 | New Freelancer | WARNING / VERIFY / score 45 | 9.00s | `['none']` |
| 3 | Utility Threat Scam | HIGH / PAUSED / score 82 | 5.02s | `urgency_pressure, threat_pressure, impersonation_attempt, irreversible_payout` |
| 4 | Crypto Syndicate Scam | CRITICAL / BLOCKED / score 100 | 2.19s | `impersonation_attempt, irreversible_payout, urgency_pressure` |

Categories/actions match the same targets as the heuristic-fallback run exactly (scores shifted slightly — e.g. scenario 1's 0→5, scenario 2's 40→45 — because the real model's independent judgment adds a small positive adjustment even on the clean cases; still comfortably within each category's range). Latency (2-9s) is genuine NVIDIA-hosted inference time, not local overhead — worth knowing for the demo, but the Payment Simulator's existing "PAYSHIELD IS CHECKING..." animated loading sequence already covers a few seconds of wait, so this fits the existing UX rather than requiring new work.

**Requirement status update:** "Rule-based and LLM-based reasoning" moves from ⚠️ Partial to ✅ Done — the LLM half is no longer just architecture-on-paper, it's a verified live call with real output feeding the real score.

**Update — Claude dropped, Gemini added as an advisory second opinion.** User has no Anthropic key and doesn't want one. Rather than lose the explanation-quality story, `llm_reasoning.py` was restructured:
- **Nemotron (primary, every request)** now generates its OWN narrative explanation as part of its existing JSON response (added a `"concern"` field to the prompt) — it no longer needs a second model to write the explanation.
- **Gemini (secondary, advisory only)** is called ONLY when the running score is already ≥30 (Medium+). It does NOT touch the score at all — deliberately, to avoid re-touching the calibration that took real effort to get right on all 4 scenarios. It returns an agree/disagree + one-sentence independent take, appended to the narrative as a cross-check line.
- This was a deliberate choice over "Gemini primary, Nemotron secondary" (which the user's own notes suggested as one option) — reasoning: Nemotron is a known-working, calibrated quantity today; making it primary keeps the demo's blast radius small if the new Gemini integration has issues, and preserves the "cheap model runs on everything, selective model only for what matters" pattern the user chose earlier for cost/latency reasons.
- `anthropic` removed from `requirements.txt`; `ANTHROPIC_API_KEY` removed from `.env.example`, replaced with `GEMINI_API_KEY`/`GEMINI_MODEL_ID`.

**Update — Gemini key added (`gemini-3.6-flash`) and debugged live.** Same pattern as the Nemotron fix: it didn't work on the first attempts, each failure was real and specific, fixed in sequence:
1. First live call: `ReadTimeout` after 20s. Second call: a clean `HTTP 503 UNAVAILABLE — model is currently experiencing high demand` *from Google's own servers* — this was actually good news, it confirmed the endpoint/auth/model-id/request-format were all already correct; Gemini was just transiently overloaded.
2. Added a single retry-with-backoff in `_call_gemini` for retryable statuses (429/500/502/503/504) and connection/timeout errors. **Found and fixed a bug in my own first version of this retry logic**: on a second consecutive timeout it `raise`d outside any enclosing try/except, which would have crashed the whole request instead of degrading gracefully. Fixed so every failure path falls through to a clean `return None` — verified by re-reading the function line by line before testing, not just by testing.
3. Next issue: `maxOutputTokens: 300` was too small — Gemini's response was getting cut off mid-JSON (raw content ending in `'```json\n{\n    "agrees'`, truncated before the closing brace). Bumped to 600, fixed.

**Verified with 3 live back-to-back calls to Medium+ scenarios:** 2/3 got genuine Gemini responses with well-written independent cross-check text (e.g. *"The transaction exhibits severe fraud indicators, combining classic utility disconnection threat tactics with a suspiciously high amount sent to an unverified, newly added UPI handle."*). The 3rd timed out on **both** retry attempts (Google-side slowness, not a bug) and degraded exactly as designed: zero crash, transaction still correctly reached CRITICAL/BLOCKED via rules+Nemotron alone, no second-opinion text simply didn't appear. That graceful-degradation behavior under real transient failure is itself a legitimate demo point for "safe autonomous decision-making" — the system was never depending on Gemini to make the right call, only to add depth when available.

**Requirement status:** the "two independent AI models, neither one alone decides" story is now fully real and demonstrated, not just architecture-on-paper — both models have been verified against live responses in this session, on top of the already-verified deterministic rules layer.

---

## Verified: all 4 demo scenarios, real backend, natural sequence

Run in order in one session (so velocity/session-state is realistic, not cherry-picked):

| # | Scenario | Amount | Result | Expected (§8) | Match |
|---|---|---|---|---|---|
| 1 | Trusted Friend (`rahul@upi`, "Lunch contribution") | ₹1,200 | `SAFE` / `SAFE` / score 0 | Low → auto-proceed | ✅ |
| 2 | New Freelancer (`priya.freelance@icici`) | ₹8,500 | `WARNING` / `VERIFY` / score 40 | Medium → confirm | ✅ |
| 3 | Utility Threat Scam (`urgent.power@upi`, urgency+threat language) | ₹25,000 | `HIGH` / `PAUSED` / score 82 | High → re-verify + confirm | ✅ |
| 4 | Crypto Syndicate Scam (flagged recipient, gift-card/crypto language) | ₹50,000 | `CRITICAL` / `BLOCKED` / score 100 | Critical → hard block | ✅ |

All 4/4 correct — this was 3/4 (Scenario 3 misclassified) before this session's fixes.

Confirm flow verified independently: VERIFY → confirm → audit log shows `pending_confirmation` then `completed`; BLOCKED → confirm attempt → 403, audit log shows `blocked`; re-confirming an already-resolved transaction → 404.

`tsc --noEmit`: clean. `npm run build`: succeeds. `python -m py_compile` on all backend files: clean. `test_api.py` (PS09-native contract): all 4 checks still pass after the shared-module changes.

---

## Build scope checklist (guardian-architecture.md §9) — updated

| In scope | Status |
|---|---|
| Simulated payment request form/API | ✅ Done |
| Five internal modules, parallelized where independent | ✅ All five are now real, not stubs (Behavioral Pattern was the last stub, closed this session) |
| Rule engine + one real LLM call for reasoning/explanation | ✅ Both models verified live: Nemotron (primary, classify+explain) on 4/4 scenarios, Gemini (secondary, advisory-only for elevated risk) on 2/3 live attempts with the 3rd gracefully degrading on transient timeout. |
| Aggregation and category mapping | ✅ Done, verified 4/4 |
| Human confirmation UI step | ✅ **Fixed this session** — real confirm/cancel/verify flow in the live React UI, backed by a real endpoint |
| Persistent audit log | ✅ Done, append-only event trail verified correct |
| Four demo scenarios wired up | ✅ **4/4 verified this session** (was 3/4) |

---

## What's still genuinely open

1. ~~Live Gemini API key never exercised~~ — **done.** Both models are now verified live. Remaining minor note: Gemini's transient failure rate observed today was roughly 1/3 (Google-side load, not our bug) — if a live demo hits that, the system degrades gracefully (verified) but the "cross-check" narrative line just won't appear for that one transaction. Not worth engineering around further; the advisory-only design already absorbs it correctly.
2. **Dashboard transaction status doesn't re-sync after confirm/cancel.** The Transaction object is added to the dashboard's list at analysis time with its risk-assessed status (SAFE/VERIFY/PAUSED); confirming or cancelling resolves the backend audit trail correctly but doesn't currently flow back to update that already-rendered card's displayed status. Cosmetic — the source of truth (audit log, backend decision) is correct either way — but worth a polish pass if time allows.
3. **Recipient list reconciliation is scoped to the 4 demo presets**, not the full `mockData.ts` dataset (other mock transactions/recipients in the dashboard are unrelated cosmetic seed data, untouched by the live pipeline).
4. **No actual browser click-through performed** — everything above is verified via curl/API calls hitting the real running servers, which exercises the exact same code path the browser would, but the visual UI (button states, modal transitions, the OTP-simulation step) has not been eyeballed in an actual browser window this session.
5. Emoji-in-print fix is applied to `main.py` only (the process's stdout/stderr are reconfigured globally, so this actually covers every module's prints too since Python's `print()` always goes through the same `sys.stdout` — but worth knowing the fix lives in one place, not scattered).

---

## Phases

### ✅ Phase 1 — Setup & Core Infrastructure
FastAPI backend, Pydantic models, five-module skeleton, JSONL audit log, initial plain HTML/JS UI (now archived).

### ✅ Phase 2 — Hybrid LLM Architecture
Nemotron (fast classification) + Claude (explanations, Medium/High only) + rules-as-final-authority, per [[hybrid_llm_approach]].

### ✅ Phase 3 — API Bug Fixes
Fixed the original 422 on `/api/confirm`, enum serialization, CORS, logging.

### ✅ Phase 4 — Frontend Integration
Adopted the provided React/TS/Vite app (archived old HTML/JS to `archived/`, not deleted). Built `pipeline.py` + `frontend_adapter.py` so both contracts share one pipeline.

### ✅ Phase 5 — Close the gaps
All items from the original Phase 5 list are done except live-API exercise (item 6, blocked on not having keys to test with):
1. ✅ Human-in-the-loop wired into the real React flow
2. ✅ Rule-engine keyword matching fixed (regex, threat category, scoped scanning)
3. ✅ Recipient ID format validation fixed for UPI handles
4. ✅ Real session/behavioral velocity tracking wired
5. ✅ Reason-list contradiction fixed
6. ⬜ Real Nemotron/Claude API paths — needs live keys, not yet exercised
7. ✅ Full 4-scenario verification (via API calls exercising the real pipeline; not yet eyeballed in an actual browser)
8. ✅ Recipient lists reconciled for the 4 demo presets (broader dataset still separate, documented as known seam)

Plus 2 bugs found and fixed that weren't on the original list: missing `red_flags` in `get_llm_reasoning()`'s return, and emoji-in-print crashing requests on Windows.

### ⚪ Phase 6 — Submission polish (next)
- Get real API keys in and confirm the live Nemotron/Claude paths work at least once (Phase 5 item 6)
- Actual browser click-through of all 4 presets + the new confirm/verify UI, screenshot or note any visual issues
- Optional: sync dashboard transaction status after confirm/cancel (item 2 above) if time allows
- Re-run `test_api.py` one more time and add equivalent smoke coverage for `/api/transactions/confirm`
- Final README skim for drift against what actually shipped
- Confirm `.env.example` is accurate, nothing secret committed, `audit_log.jsonl` from this session's testing is fine to ship or reset per your preference (it's gitignored either way)

---

## Quick reference: what "done" currently means

Run both servers, open the Payment Simulator, submit any of the 4 presets: real rules + real behavioral/velocity tracking + fallback LLM reasoning run → correct risk score/category/action → for VERIFY/PAUSED, the UI now genuinely stops and waits for your explicit confirm or cancel (with a simulated identity check gating PAUSED) → decision is written to `audit_log.jsonl` as a two-step trail (initial analysis, then resolution) → BLOCKED is a hard stop with no override, verified via a direct attempt to bypass it. That loop is real, tested against the actual running backend, and matches the architecture doc's four required demo scenarios exactly. What's left is mostly "prove it with a real LLM key" and "look at it in an actual browser," not "build more of it."
