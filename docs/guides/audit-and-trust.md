# Agent Audit & Trust

Peaky Peek reframes an agent run as an **audit record**, not just an execution trace. The job of the audit layer is to make agent behavior **visible, verifiable, and reliable** so a human operator can audit a run without guessing.

> Make AI agent behavior visible, verifiable, and reliable. Show what the agent did, why it did it, what data it used, what result it produced, and where it failed or became unreliable.

This guide covers the five-question model, the claim verification taxonomy, the trust score, the API surface, and worked examples of an audited session and a failure report.

---

## The five operator questions

Every session produces a report that answers these five questions. They are the dominant interaction pattern in the Audit UI panel and the top-level shape of the JSON report.

| Question | What it surfaces |
|----------|------------------|
| **What happened?** | Exact sequence: tool calls, model calls, decisions, retries, edits, outputs. |
| **Why?** | Stated or inferred rationale, alternatives considered, confidence, trigger for each important decision. |
| **With what evidence?** | Input sources used: user input, retrieved documents, tool parameters, tool results, prompt fragments. |
| **With what result?** | Success/failure, returned data, state changes (checkpoints), downstream effects. |
| **Where did it fail?** | First bad decision, ignored evidence, weak/empty tool data, contradictions, plan drift, repeated failed strategies, policy violations, and the downstream damage. |

---

## Claim verification taxonomy

Every `decision` event in the trace is treated as a **claim** and classified deterministically. No LLM judging, no randomness — the status is derivable from captured fields.

| Status | Meaning |
|--------|---------|
| `verified` | Backed by a successful tool result or user-provided input. |
| `partially_verified` | Carries evidence (e.g. a retrieved document) but it does not resolve to a tool/user fact. |
| `contradicted` | A confident decision whose downstream causal subtree contains a failure. |
| `unsupported` | Confident claim (confidence ≥ 0.5) made with **no** evidence. |
| `unverified` | Low-confidence claim with no evidence — an unverified assumption. |
| `stale` | Reserved for evidence older than a staleness window. |

Evidence `source` values are grouped into:

- **Tool-backed facts** — `tool_result`, `tool`, `function`, `api`, `tool_call`
- **User-provided facts** — `user_input`, `user`, `human`, `operator`
- **Retrieved evidence** — `retrieved`, `retrieval`, `document`, `search`, `memory`, `rag`
- **Inferred** — anything else

---

## Trust / reliability score

Each session gets an **explainable** trust score in `[0.0, 1.0]` banded `low` / `medium` / `high`. It is a transparent weighted blend of inspectable sub-metrics:

```
score = 0.30
      + 0.25 * evidence_coverage        # decisions that carry evidence refs
      + 0.20 * verification_rate         # claims that are fully verified
      + 0.10 * policy_compliance         # 1 - policy_violations / decisions
      + 0.10 * recovery_rate             # successful repairs / failures
      - 0.15 * failure_severity          # max causal severity of failures
      - 0.05 * contradiction_rate        # contradicted claims / decisions
      - 0.05 * repeated_failed_strategy  # bounded count of looped tool failures
```

Every component is returned alongside the score in `trust.components`, and `trust.explanation` is a single human-readable line showing how the number was derived. If you disagree with a score, you can point at the exact term.

---

## Risk signals (deterministic)

The engine emits these signal types, each anchored to an `event_id`:

| Signal | Triggered when |
|--------|----------------|
| `unsupported_claim` | A decision is confident but evidence-free. |
| `missing_evidence` | A high-confidence decision lacks evidence references. |
| `confidence_evidence_mismatch` | Confidence is unjustified by attached evidence. |
| `contradiction` | A confident decision is followed by a failure in its subtree. |
| `weak_evidence` | A decision relies on non-tool-verified evidence. |
| `repeated_failed_strategy` | The same tool fails 2+ times. |
| `plan_drift` | A drift event, tool-loop alert, or status error. |
| `policy_violation` | A policy/safety rule breach. |

---

## API surface

### `GET /api/sessions/{session_id}/audit`

Returns a `SessionAuditResponse` — the full audit report. It reuses the session's existing failure explanations so it stays consistent with the replay / causal analysis surfaced elsewhere.

```bash
curl http://localhost:8000/api/sessions/<id>/audit
```

Top-level shape:

```
SessionAuditResponse
└── audit: SessionAuditReport
    ├── objective, final_outcome
    ├── questions: { what_happened, why, evidence, outcome, where_it_failed }
    ├── claims[]           # every decision + its verification status
    ├── signals[]          # deterministic risk signals
    ├── failures[]         # localized failure root-cause suspects
    ├── critical_decisions[]
    ├── trust: { score, band, components, explanation }
    └── review_points[]    # where a human should look
```

The report is produced by `collector.audit.SessionAuditEngine` (`collector/audit/audit_engine.py`) and reuses `CausalAnalyzer` and `FailureDiagnostics` for failure localization rather than re-deriving it.

---

## Example: one audited session

A weather agent that made two decisions — one grounded in a tool result, one asserted confidently with no evidence that then failed.

```json
{
  "session_id": "sess_weather_001",
  "audit": {
    "session_id": "sess_weather_001",
    "objective": "What's the weather in Seattle?",
    "final_outcome": "completed with 1 failure signal(s)",
    "questions": {
      "what_happened": {
        "summary": "9 events: 2 tool calls, 1 model calls, 2 decisions, 1 retries, 1 failures.",
        "event_count": 9,
        "tool_calls": 2,
        "tool_results": 2,
        "llm_calls": 1,
        "decisions": 2,
        "retries": 1,
        "edits": 0
      },
      "why": {
        "decisions_with_rationale": [
          {
            "event_id": "evt_dec_1",
            "headline": "call_weather_api",
            "rationale": "User asked for weather; ground the answer in a live tool result.",
            "confidence": 0.9,
            "alternatives_considered": 1
          },
          {
            "event_id": "evt_dec_2",
            "headline": "forecast_without_data",
            "rationale": "Predict rain tomorrow.",
            "confidence": 0.8,
            "alternatives_considered": 0
          }
        ]
      },
      "evidence": {
        "tool_backed_facts": 1,
        "user_input_facts": 1,
        "retrieved_facts": 0,
        "evidence_sources": ["tool_backed", "user_provided"],
        "coverage_of_decisions": 0.5
      },
      "outcome": {
        "success_count": 1,
        "failure_count": 1,
        "failed_tool_results": 1,
        "state_snapshots": 0,
        "failures": [
          {
            "event_id": "evt_tool_fail_1",
            "mode": "tool_error",
            "symptom": "forecast_api returned HTTP 503",
            "likely_cause_event_id": "evt_dec_2"
          }
        ]
      },
      "where_it_failed": {
        "first_failure": "evt_tool_fail_1",
        "first_bad_decision": "evt_dec_2",
        "failures": 1,
        "top_signals": [
          { "type": "unsupported_claim", "severity": "high", "message": "Decision \"forecast_without_data\" asserted at confidence 0.80 without any evidence." },
          { "type": "contradiction", "severity": "high", "message": "Confident decision \"forecast_without_data\" was followed by a failure in its causal subtree." },
          { "type": "repeated_failed_strategy", "severity": "medium", "message": "Tool \"forecast_api\" failed 2 times — repeated failed strategy." }
        ]
      }
    },
    "claims": [
      {
        "event_id": "evt_dec_1",
        "event_type": "decision",
        "headline": "call_weather_api",
        "claim": "call_weather_api",
        "rationale": "User asked for weather; ground the answer in a live tool result.",
        "confidence": 0.9,
        "alternatives_considered": 1,
        "evidence_refs": ["evt_user_1", "evt_tool_ok_1"],
        "evidence_sources": ["tool_backed", "user_provided"],
        "verification_status": "verified",
        "verification_basis": "backed by a successful tool result",
        "contradicted": false,
        "timestamp": "2026-07-13T09:00:01+00:00"
      },
      {
        "event_id": "evt_dec_2",
        "event_type": "decision",
        "headline": "forecast_without_data",
        "claim": "Predict rain tomorrow.",
        "rationale": "Predict rain tomorrow.",
        "confidence": 0.8,
        "alternatives_considered": 0,
        "evidence_refs": [],
        "evidence_sources": [],
        "verification_status": "contradicted",
        "verification_basis": "decision subtree contains a failure event",
        "contradicted": true,
        "timestamp": "2026-07-13T09:00:04+00:00"
      }
    ],
    "signals": [
      { "event_id": "evt_dec_2", "type": "unsupported_claim", "severity": "high", "message": "Decision \"forecast_without_data\" asserted at confidence 0.80 without any evidence." },
      { "event_id": "evt_dec_2", "type": "confidence_evidence_mismatch", "severity": "high", "message": "Confidence 0.80 is unjustified: no evidence attached." },
      { "event_id": "evt_dec_2", "type": "contradiction", "severity": "high", "message": "Confident decision \"forecast_without_data\" was followed by a failure in its causal subtree." },
      { "event_id": "evt_tool_fail_1", "type": "repeated_failed_strategy", "severity": "medium", "message": "Tool \"forecast_api\" failed 2 times — repeated failed strategy." }
    ],
    "failures": [
      {
        "event_id": "evt_tool_fail_1",
        "event_type": "tool_result",
        "headline": "forecast_api",
        "mode": "tool_error",
        "symptom": "forecast_api returned HTTP 503",
        "likely_cause": "Agent called forecast_api without grounding the prediction in a tool result.",
        "likely_cause_event_id": "evt_dec_2",
        "confidence": 0.74,
        "supporting_event_ids": ["evt_dec_2"],
        "position": 6
      }
    ],
    "critical_decisions": [
      { "event_id": "evt_dec_2", "verification_status": "contradicted", "confidence": 0.8 },
      { "event_id": "evt_dec_1", "verification_status": "verified", "confidence": 0.9 }
    ],
    "trust": {
      "score": 0.4933,
      "band": "medium",
      "components": {
        "evidence_coverage": 0.5,
        "verification_rate": 0.5,
        "contradiction_count": 1,
        "contradiction_rate": 0.5,
        "failure_severity": 0.6,
        "recovery_rate": 0.0,
        "policy_compliance": 1.0,
        "decision_count": 2,
        "failure_count": 1
      },
      "explanation": "trust=0.49 (medium) from evidence_coverage=0.50, verification_rate=0.50, policy_compliance=1.00, recovery_rate=0.00, failure_severity=0.60, contradictions=1."
    },
    "review_points": [
      { "event_id": "evt_dec_2", "priority": "high", "reason": "Decision \"forecast_without_data\" is contradicted (confidence 0.80)." },
      { "event_id": "evt_tool_fail_1", "priority": "high", "reason": "Failure (tool_error): forecast_api returned HTTP 503" }
    ]
  }
}
```

Reading the report: the grounded decision is `verified`; the evidence-free prediction is `contradicted` because its subtree contains the `forecast_api` failure; the trust score is `medium` (0.49) because evidence coverage, verification rate, and recovery are all weak while a contradiction and a failure are present. A human reviewer is pointed straight at `evt_dec_2` and `evt_tool_fail_1`.

> Note: `critical_decisions[]` entries share the full claim shape shown in `claims[]` above — abbreviated here for readability.

---

## Example: one failure report

A single entry from `audit.failures[]` — a localized failure with its root-cause suspect. This is the same shape surfaced in the UI's **Where it failed** card.

```json
{
  "event_id": "evt_tool_fail_1",
  "event_type": "tool_result",
  "headline": "forecast_api",
  "mode": "tool_error",
  "symptom": "forecast_api returned HTTP 503",
  "likely_cause": "Agent called forecast_api without grounding the prediction in a tool result.",
  "likely_cause_event_id": "evt_dec_2",
  "confidence": 0.74,
  "supporting_event_ids": ["evt_dec_2"],
  "position": 6
}
```

Fields:

- **`mode`** — failure category (e.g. `tool_error`, `llm_error`, `agent_error`).
- **`symptom`** — what was observed.
- **`likely_cause`** / **`likely_cause_event_id`** — the suspected upstream decision and its id; in the UI, this is the "inspect cause" jump target.
- **`supporting_event_ids`** — the events that justify the diagnosis.
- **`confidence`** — confidence in the root-cause attribution.
- **`position`** — index of the failure in the event sequence (lower = earlier).

---

## How it stays deterministic

The audit engine reads existing event fields (`confidence`, `evidence`, `evidence_event_ids`, `alternatives`, `chosen_action`, `reasoning`, `upstream_event_ids`) via `collector.intelligence.helpers.event_value`, so it works on both typed SDK events and events reconstructed from storage. It reuses:

- `CausalAnalyzer` — causal-graph + severity + headline clipping
- `FailureDiagnostics` — failure localization (`is_failure_event`, `build_failure_explanations`)

No schema migration was required — the event model already carried the audit fields. The layer is a unified 5-questions + trust-score + verification-status view over existing primitives.

---

## What this is not

- Not a generic observability dashboard — the unit of analysis is one agent run, audited as evidence.
- Not opaque "AI insights" — every status, signal, and score term is derivable from captured fields.
- Not a replacement for replay or drift detection — it composes them. Replay shows *how* a run unfolded; audit shows *whether you should trust it*.
