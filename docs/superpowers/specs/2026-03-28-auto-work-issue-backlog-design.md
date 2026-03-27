# Auto-Work Issue Backlog Design

**Date**: 2026-03-28
**Status**: Approved
**Scope**: 15 auto-work GitHub issues organized in priority-first tiers

## Background

The auto-worker (`scripts/auto-worker.sh`) picks up GitHub issues labeled `auto-work` in FIFO order, creates a worktree, implements the fix, validates, and opens a PR. Four issues currently exist (#10-#13), all code health refactors. Issue #10 was completed (commit `c2cb1d3`) but left open.

This design defines the next batch of 15 issues: 5 code health, 5 test coverage, 5 feature completion. Balanced split, bite-sized to medium scope, each with clear acceptance criteria.

## Organizing Principle: Priority-First Queue

Issues are tiered by autonomous-work safety:
- **Tier 1 (Code Health)**: Self-contained complexity/size reductions, zero contract risk
- **Tier 2 (Test Coverage)**: Self-validating tests that add a safety net
- **Tier 3 (Feature Completion)**: Well-scoped feature gaps with clear specs

The auto-worker processes FIFO, so ordering within each tier matters. We front-load the safest tasks.

## Tier 1: Code Health (5 issues)

### CH-1: Close issue #10 (already completed)

**Context**: Issue #10 ("Refactor mock_smart_replay test fixture") was implemented in commit `c2cb1d3` but never closed.

**Action**: Close the GitHub issue with a comment referencing the commit.

**Acceptance**: Issue #10 is closed.

---

### CH-2: Simplify `detect_oscillation` (complexity 15 -> <10)

**Context**: `collector/detection.py:11` — `detect_oscillation` has cyclomatic complexity 15.

**What to do**:
- Extract the window comparison logic into a focused helper function
- Extract the pattern detection (A->B->A matching) into a separate function
- Reduce nesting in the main function body

**Acceptance**:
- Function complexity drops below 10
- All existing tests pass
- No behavior changes

---

### CH-3: Simplify `generate_highlights` (complexity 15 -> <10)

**Context**: `collector/highlights.py:23` — `generate_highlights` has cyclomatic complexity 15.

**What to do**:
- Extract the ranking/filtering logic into a helper
- Separate event categorization from highlight assembly
- Reduce branching in the main function

**Acceptance**:
- Function complexity drops below 10
- All existing tests pass
- No behavior changes to highlight output

---

### CH-4: Simplify `_send_with_retry` (complexity 15 -> <10)

**Context**: `agent_debugger_sdk/transport.py:174` — `_send_with_retry` has cyclomatic complexity 15.

**What to do**:
- Extract the retry decision logic (should retry? backoff calculation?) into helpers
- Separate the actual send attempt from the retry orchestration
- Keep the public transport interface identical

**Acceptance**:
- Function complexity drops below 10
- All existing tests pass
- Transport behavior (retry counts, backoff, error handling) unchanged

---

### CH-5: Simplify `identify_low_value_segments` (complexity 16 -> <10)

**Context**: `collector/replay_collapse.py:35` — `identify_low_value_segments` has cyclomatic complexity 16.

**What to do**:
- Extract segment scoring into its own function
- Separate the threshold comparison and grouping logic
- Keep segment identification results identical

**Acceptance**:
- Function complexity drops below 10
- All existing tests pass
- No changes to segment identification output

## Tier 2: Test Coverage (5 issues)

### TC-1: Add tests for `collector/highlights.py`

**Context**: The highlight generation module has zero test coverage. It generates event highlights and rankings used in the smart replay feature.

**What to do**:
- Create `tests/test_highlights.py`
- Test highlight generation with various event sets
- Test ranking logic
- Test edge cases: empty events, single event, all same-type events, events with missing fields
- Verify highlight count limits are respected

**Acceptance**:
- At least 15 tests covering happy paths and edge cases
- All tests pass
- Tests cover the public API of the highlights module

---

### TC-2: Add tests for `collector/detection.py`

**Context**: The detection module (oscillation detection, pattern matching) has zero test coverage.

**What to do**:
- Create `tests/test_detection.py`
- Test `detect_oscillation` with known oscillating sequences
- Test with non-oscillating sequences (negative cases)
- Test window boundary behavior
- Test edge cases: empty sequences, single element, window larger than sequence

**Acceptance**:
- At least 10 tests covering detection functions
- Both positive and negative test cases
- All tests pass

---

### TC-3: Add tests for `storage/search.py`

**Context**: `search_sessions` (complexity 14) in `storage/search.py` has zero test coverage. Handles session search queries.

**What to do**:
- Create `tests/test_search.py`
- Test query parsing and result ranking
- Test tenant isolation (searches only return results for the correct tenant)
- Test empty result sets
- Test special characters in queries
- Use in-memory database fixtures for isolation

**Acceptance**:
- At least 15 tests
- Tenant isolation is explicitly tested
- All tests pass with in-memory fixtures (no external DB dependency)

---

### TC-4: Add API contract tests for session routes

**Context**: `api/session_routes.py` has zero test coverage. Session CRUD is a core API surface.

**What to do**:
- Create `tests/test_session_routes.py` (or extend existing)
- Test session list endpoint with filter parameters
- Test session detail endpoint
- Test error responses (404 for missing session, invalid IDs)
- Test response schema compliance

**Acceptance**:
- At least 15 tests covering CRUD operations
- Error responses tested
- Response schemas validated
- All tests pass

---

### TC-5: Add tests for `collector/baseline.py`

**Context**: Baseline computation (`compute_baseline_from_sessions`, complexity 22) and drift detection (`detect_drift`, complexity 14) have zero test coverage.

**What to do**:
- Create `tests/test_baseline.py`
- Test baseline aggregation from session data
- Test drift detection with known drift scenarios
- Test drift thresholds and scoring
- Test edge cases: single session, identical sessions, empty session lists

**Acceptance**:
- At least 15 tests
- Both baseline computation and drift detection covered
- All tests pass

## Tier 3: Feature Completion (5 issues)

### FC-1: Implement fix note endpoint

**Context**: The frontend calls `addFixNote()` but `POST /api/sessions/{id}/fix-note` doesn't exist.

**What to do**:
- Add route to `api/session_routes.py` (or appropriate route file)
- Add service method to handle fix note creation
- Add storage operation to persist the note
- Add response schema

**Acceptance**:
- `POST /api/sessions/{id}/fix-note` returns 200 with saved note
- Frontend `addFixNote()` works end-to-end
- Ruff and existing tests pass

---

### FC-2: Implement checkpoint delta endpoint

**Context**: Frontend types define checkpoint structures but there's no endpoint to compute deltas between consecutive checkpoints.

**What to do**:
- Add route `GET /api/sessions/{id}/checkpoints/deltas`
- Implement delta calculation that compares state/memory between adjacent checkpoints
- Add response schema

**Acceptance**:
- Endpoint returns state and memory deltas between checkpoints
- Response matches frontend type expectations
- Ruff and existing tests pass

---

### FC-3: Add "Replay from Here" button to frontend

**Context**: The design spec (`2026-03-27-phase1-why-button-smart-replay-design.md`) mentions replay-from-here functionality, but the UI has no trigger for it.

**What to do**:
- Add a "Replay from Here" button to the event detail panel in `frontend/src/App.tsx` (or the relevant event detail component)
- On click: set replay mode to true and set focus event ID to the selected event via the Zustand store
- Wire into existing store actions (`setReplayMode`, `setFocusEvent` or equivalent)

**Acceptance**:
- Button appears in event detail panel
- Clicking it activates replay mode focused on that event
- Frontend build passes
- No regressions to existing replay behavior

---

### FC-4: Add database migrations for missing tables

**Context**: `AnomalyAlertModel` and `FailureClusterModel` are referenced in code but have no database tables.

**What to do**:
- Add migration files for both tables
- Add SQLAlchemy model definitions
- Ensure migrations are idempotent

**Acceptance**:
- Both tables created by migration
- Models match existing type definitions
- Existing migrations still apply cleanly

---

### FC-5: Simplify and test `collector/scorer.py`

**Context**: `score` method in `collector/scorer.py:30` has complexity 13 and zero test coverage.

**What to do**:
- Simplify the scoring function (reduce complexity below 10)
- Extract event type scoring into a lookup-friendly structure
- Add test file `tests/test_scorer.py`
- Cover scoring for all event types, edge cases, and weight configurations

**Acceptance**:
- Complexity drops below 10
- At least 10 tests added
- Scoring output unchanged for all event types
- All tests pass

## Issue Template

Each auto-work issue follows this structure:

```markdown
## Context
[Why this issue exists — debt scan reference, spec reference, or gap analysis]

## What to do
- [Numbered list of specific actions]

## Acceptance
- [Measurable criteria that prove the issue is complete]
```

## Issue Creation Order

Issues should be created in this exact order so FIFO picks them up tier-by-tier:

1. CH-1 (close #10)
2. CH-2 (detect_oscillation)
3. CH-3 (generate_highlights)
4. CH-4 (_send_with_retry)
5. CH-5 (identify_low_value_segments)
6. TC-1 (highlights tests)
7. TC-2 (detection tests)
8. TC-3 (search tests)
9. TC-4 (session routes tests)
10. TC-5 (baseline tests)
11. FC-1 (fix note endpoint)
12. FC-2 (checkpoint deltas)
13. FC-3 (replay from here button)
14. FC-4 (database migrations)
15. FC-5 (scorer simplify + test)

## Pre-existing Issues

Issues #10-#13 should be evaluated:
- **#10**: Close (already completed)
- **#11**: Extract shared adapter base class — keep open, valid work
- **#12**: Simplify compute_baseline_from_sessions — keep open, valid work
- **#13**: Split large adapter files — keep open, valid work

The new issues don't duplicate #11-#13. They tackle different complexity hotspots and gaps.

## Success Metrics

- All 15 issues created with `auto-work` label
- Auto-worker can complete at least 3 issues per run without human intervention
- Each PR references the issue and passes `ruff check` + relevant tests
- Issue #10 closed
