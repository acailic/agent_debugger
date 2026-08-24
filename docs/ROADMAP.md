# Peaky Peek Roadmap

This is the **living roadmap** for the agent audit & trust console. It supersedes
all earlier planning documents for prioritization purposes (see
[Superseded Documents](#superseded-documents)); those remain useful as theme
reference and history.

**Maintenance rule:** update this file as part of each release — move finished
work into [Recently Shipped](#recently-shipped), refresh milestones, and re-rank
the experiment backlog. Do not create new standalone plan documents; extend this
one.

Last updated: 2026-08-24

---

## Current State

The core product loop works end-to-end, locally and deterministic:

- **Audit & trust layer** — a per-session audit report answering the five
  operator questions (what / why / evidence / outcome / where-failed), with
  deterministic claim verification (verified · partially verified · contradicted ·
  unsupported · unverified · stale), risk signals, failure localization, an
  explainable trust score, and a human-auditable session summary
- **Drill-down surfaces** — per-decision justification, evidence-provenance
  graph (including uncited-fact callouts), fleet-level audit portfolio,
  timeline audit flags in the frontend
- **Debugging toolkit** — replay with checkpoints, causal graph / root-cause
  analysis, session comparison and divergence detection, multi-agent swimlanes
  with coordination/emergent-behavior analysis, stepper (breakpoints/branches),
  reasoning editor, policy and violation analysis
- **Research features** — frame lifetime traces, backward failure attribution,
  conformal uncertainty/prediction-interval/risk endpoints
- **Platform** — tenant-aware storage, auth middleware, redaction pipeline,
  analytics DB, CI with lint + test matrix (Python 3.10–3.12) and a 70% coverage
  gate

Test suite: 3,000+ tests passing.

## Milestones

### M1 — Audit depth (in progress)

Make the audit layer measurably trustworthy, not just present.

1. **Deterministic goal-drift score** — per-decision "objective still
   referenced?" series; upgrades the existing plan-drift signal from anecdote
   to measurement. *Delivered: 2026-08-15.*
2. **Success-flow deviation advisory** — localize a failing run's first
   departure from how similar successful runs flow, built on the divergence
   detector; advisory-only, never affects the trust score.
   *Delivered: 2026-08-15.*
3. **Who&When benchmark harness** — evaluate failure localization against the
   public Who&When annotated failure logs; publish an external accuracy number.
   *Harness delivered 2026-08-15; full-dataset run pending.*
4. **Verdict-card stakes + named trust bands** — stakes line (resources
   touched, writes vs reads) and act / verify-first / do-not-act bands.
   *Delivered: 2026-08-15.*

### M2 — Operator experience

Reduce the distance between "report exists" and "operator decides".

1. Minimal re-execution set — the smallest sub-graph to re-run to confirm or
   invalidate a suspect claim (from the provenance survey note)
2. Explanation maturity — failure narratives (symptom / mechanism / evidence /
   next inspection point) as a first-class surface
   *Delivered: 2026-08-24 (`collector/audit/failure_narrative.py`, wired into
   the audit report + AuditPanel narrative block).*
3. Replay restore semantics beyond checkpoint slicing
4. Seeded benchmark corpora + UI smoke workflows around them

### M3 — Platform at scale

Make the research-backed debugger viable outside a strong local demo.

1. `api/services.py` decomposition into cohesive service modules
   *Delivered: 2026-08-15 (session_analysis / causal / similarity split with
   re-exports).*
2. Cross-session replay clustering and retention tiers
3. Finish cloud/auth wiring around the accepted ADRs; enforce tenant isolation
   end-to-end
4. Typing-debt cleanup — drive the pyright baseline (see
   `pyrightconfig.json`, ~280 errors as of 2026-08) to zero so the advisory
   type-check step can gate again
4. Wire redaction into every ingestion and persistence path

## Research Experiment Backlog

Each row is the "best next experiment" from a note in [`docs/papers/`](papers/README.md).
Rank by how often real operators ask the question it answers.

| Paper note | Experiment | Status |
|---|---|---|
| From Agent Traces to Trust (provenance survey) | Map one session onto the survey's relation taxonomy; find expressible-vs-missing relations | not started |
| Evaluating Goal Drift | Per-step adherence series vs trust score | **shipped** (M1.1) |
| Who&When | External accuracy on public failure logs | harness ready (M1.3) |
| OAT / Flow of Success | First-divergence heuristic vs audit engine's first bad decision | **shipped** (M1.2) |
| Calibrated Trust | Stakes line + trust bands in verdict card | **shipped** (M1.4) |
| AgentTrace | Causal graph completeness check against root-cause queries | not started |
| XAI for Coding Agent Failures | Structured explanation bundle for one failed session | **shipped** (M2.2) |
| FailureMem | Failure-memory reuse across similar sessions | not started |
| MSSR | Adaptive replay ranking by replay value | not started |
| Act-or-Refuse | Refusal-behavior surfaces in the audit report | not started |
| Policy-Parameterized Prompts | Multi-agent policy comparison views | not started |
| CXReasonAgent | Evidence-citation coverage metric for decisions | not started |
| NeuroSkill | Operator-state awareness (stretch; low priority) | not started |
| REST | Guided exploration over large trace graphs | not started |
| Neural Debugger for Python | Learned pre-execution checks (stretch) | not started |

## Non-Goals

Carried forward from the research implementation plan:

- do not reproduce full paper training methods
- do not store unrestricted chain-of-thought
- do not add speculative complexity before one complete workflow ships
- the debugger is not itself the safety system

## Recently Shipped

- 2026-08-24 — full-stack e2e scenario suite (`tests/e2e/`, 46 tests): real
  uvicorn subprocess + real SDK HTTP transport + real SQLite + authenticated
  tenant; 11 real-world scenario agents (grounded, contradicted, stale
  evidence, retry loop, goal drift, policy refusal, recovery, checkpoints,
  multi-agent crew, twin triage runs, operator utilities). The suite
  immediately caught and fixed three real product bugs in the HTTP delivery
  path: collector ingest dropped all typed event fields and regenerated
  event ids (breaking evidence references), checkpoints were silently lost
  in transport mode (no send_checkpoint/endpoint), and audit verdicts
  mis-scored enum repair outcomes + false-stale self-supersession
- 2026-08-24 — frontend load-crash fixes: zustand v5 object selectors in
  TraceView/InspectView wrapped in useShallow (infinite re-render on load),
  TraceTimeline null-duration guard (`duration_ms` arrives as JSON null);
  first audit-panel + failure-narrative screenshots in README
- 2026-08-24 — failure narratives (M2.2): symptom / mechanism / evidence /
  next-inspection bundle in every audit report, normalized failure-mode
  taxonomy, honest weakness note + capped confidence when no cause is
  localized; first AuditPanel narrative surface
- 2026-08-15 — goal-drift score, success-flow advisory, Who&When harness,
  verdict stakes + trust bands (M1), services decomposition (M3.1), API route
  tests for research/swimlane endpoints, 5 new research paper notes
- 2026-07 — audit & trust system: engine, justification, evidence graph,
  portfolio, staleness detection, session summary/verdict card, timeline audit
  flags, frontend panels (gnhf 1–19)
- 2026-07 — telemetry SDK unit tests; OTLP exporter test hermeticity

## Superseded Documents

The following are historical; do not plan against them:

- [`docs/research/research-implementation-plan.md`](research/research-implementation-plan.md) — superseded 2026-08-15; still the best theme reference
- [`docs/plans/improvement-roadmap.md`](plans/improvement-roadmap.md) — superseded 2026-06
- [`docs/plans/NO_BRAINER_FEATURES_PLAN.md`](plans/NO_BRAINER_FEATURES_PLAN.md) and related no-brainer docs — superseded 2026-06
- [`docs/plans/TOP_0.1_PERCENT_STRATEGY.md`](plans/TOP_0.1_PERCENT_STRATEGY.md) — superseded 2026-06
- [`docs/research/competitive-roadmap.md`](research/competitive-roadmap.md), [`docs/research/EDGE_OF_TECHNICAL_POSSIBILITIES.md`](research/EDGE_OF_TECHNICAL_POSSIBILITIES.md) — superseded 2026-06; positioning reference only
