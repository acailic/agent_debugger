# Changelog

All notable changes to Peaky Peek will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-08-15

The audit & trust release: every run now answers the five operator questions
(what happened, why, with what evidence, with what result, where it failed)
with deterministic claim verification and an explainable trust score.

### Added

#### Agent audit & trust system
- `SessionAuditEngine` — per-session audit report answering the five operator
  questions, with deterministic claim verification
  (verified · partially_verified · contradicted · unsupported · unverified ·
  stale), risk signals, failure localization, and an explainable trust score;
  exposed via `GET /api/sessions/{id}/audit`
- Timestamp-based staleness detection — decisions built on superseded evidence
  are classified `stale` with a matching `stale_evidence` signal
- Per-decision justification (`GET /api/sessions/{id}/decisions/{event_id}/justification`)
- Evidence-provenance graph (`GET /api/sessions/{id}/evidence-graph`), including
  available facts the agent had but never cited
- Cross-session audit portfolio (`GET /api/audit/portfolio`) — fleet-level
  trust/verification/failure aggregates, worst-trust-first
- Human-auditable session summary (verdict + tldr + trust line + markdown
  narrative) rendered as a verdict card
- Goal-drift score — deterministic per-decision objective-adherence series
  with a conservative drift flag and `goal_drift` risk signal
- Verdict-card stakes line (mutating vs read-only tool calls) and named trust
  bands (act / verify-first / do-not-act)
- Success-flow deviation advisory (`GET /api/sessions/{id}/success-flow`) —
  first-divergence localization against a successful reference run;
  advisory-only, never feeds the trust score
- Who&When benchmark harness (`collector/audit/who_when.py` +
  `scripts/benchmark_who_when.py`) — scores the engine's deterministic failure
  attribution against the public annotated benchmark

#### Frontend
- AuditPanel (trust header, five-questions grid, verification badges,
  localized failures, review points, risk signals, goal-drift block)
- EvidenceGraphPanel, DecisionJustificationPanel, PortfolioAuditPanel
- Inline audit risk markers and an "Audit flags" filter on the trace timeline

#### Documentation
- Living `docs/ROADMAP.md` superseding earlier planning docs; audit-and-trust
  guide with example audited-session and failure-report outputs; 5 new
  research paper notes (provenance survey, goal drift, Who&When, OAT
  success-flow, calibrated trust); README repositioned as an agent
  audit/trust console

### Changed
- `api/services.py` split into a cohesive `api/services/` package
  (sessions / ingestion / similarity / causal / analysis) behind a
  backward-compatible facade — all existing imports keep working
- Research-route computation extracted into pure functions in
  `api/services/research`

### Internal
- API route tests for the research and swimlane endpoints (previously
  untested HTTP layer); unit tests for `agent_debugger_sdk/telemetry`
- Shared `unique_id()` test helper; documented the local coverage
  measurement caveat for ASGI route handlers

## [0.1.19] - 2026-06-13

### Internal
- Deduplicated StrEnum Python 3.10 compatibility shim into `agent_debugger_sdk.core._compat`
- Added composite database indexes for events, sessions, checkpoints
- Replaced module-level `_shared_app` pattern with session-scoped `shared_app` fixture
- Enabled pyright type checking in CI

## [0.1.18] - 2026-06-10

### Fixed
- Corrected stepper test fixture and assertions

### Added
- Agent stepper, swimlane debugger, and violation detection features
- Reasoning editor and divergence detection features

## [0.1.17] - 2026-06-08

### Added
- Research-driven event behavior features
- Frame tracer and divergence detector

### Fixed
- Resolved all ruff lint errors across SDK and test files
- Python 3.10 compatibility for StrEnum in core modules
