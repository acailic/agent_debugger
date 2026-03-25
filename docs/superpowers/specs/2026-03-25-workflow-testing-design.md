# Workflow-Based Testing Design

**Date**: 2026-03-25
**Status**: Draft
**Author**: Claude (via brainstorming session)

## Summary

Design a testing approach that verifies Peaky Peek helps developers debug real agent problems, not just "does it capture events." Tests are organized by developer workflow, use record/replay for CI compatibility, and focus on happy path + one failure mode per workflow.

---

## Problem Statement

### Current State
- 8 synthetic benchmark scenarios that test event capture
- Unit tests for individual components
- Integration tests with mocked libraries
- API contract tests

### Gaps
- Tests verify "does it capture events" not "does it help debug"
- No tests for real debugging workflows (root cause hunting, safety auditing, reproducibility)
- No coverage of LLM non-determinism handling
- Mocked libraries, not real framework integration

### Goals
1. **Reliability** - Catch more bugs before they ship
2. **Confidence** - Prove the tool works with real agent frameworks

---

## Design Decisions

### D1: Organize Tests by Developer Workflow

**Decision**: Tests are organized by what the developer is trying to accomplish, not by component or feature.

**Why**: Aligns testing with real usage. A developer asks "why did my agent fail?" not "does upstream_event_ids work?"

**Workflows covered**:
1. Root cause hunting - "Something went wrong, find the decision that caused it"
2. Safety auditing - "Did my agent do anything dangerous or unexpected?"
3. Reproducibility - "This worked yesterday, why does it fail now?"

### D2: Record/Replay for CI Compatibility

**Decision**: Use VCR-style record/replay. Run real agents locally to record cassettes, replay deterministically in CI.

**Why**:
- No API keys needed in CI
- Real framework behavior captured in recordings
- Fully reproducible test runs
- Recordings can be refreshed periodically

**Trade-offs**:
- Recordings can go stale if APIs change
- Need to maintain cassettes
- Initial recording requires manual effort

### D3: Happy Path + One Failure Per Workflow

**Decision**: Each workflow has 2 tests: happy path (workflow succeeds) and one failure mode (workflow reveals a problem).

**Why**:
- Pragmatic scope - 6 total tests
- Covers the 80% case without over-engineering
- Easy to understand and maintain
- Can add more failure modes later if needed

### D4: LLM Non-Determinism as Primary Reproducibility Concern

**Decision**: Focus reproducibility tests on handling LLM non-determinism (same prompt, different outputs).

**Why**:
- Most common source of "it worked yesterday" problems
- Temperature, sampling, model updates all cause variation
- Record/replay directly addresses this

---

## Test Structure

```
tests/
├── workflows/
│   ├── __init__.py
│   ├── conftest.py                              # Shared fixtures
│   ├── test_root_cause_hunting.py
│   ├── test_safety_auditing.py
│   └── test_reproducibility.py
│
├── cassettes/
│   ├── root_cause/
│   │   ├── tool_failure_to_decision.yaml        # Happy path
│   │   └── hallucinated_evidence.yaml           # Failure mode
│   ├── safety/
│   │   ├── enumerate_safety_events.yaml         # Happy path
│   │   └── missed_policy_violation.yaml         # Failure mode
│   └── reproducibility/
│       ├── checkpoint_replay.yaml               # Happy path
│       └── session_diff_divergence.yaml         # Failure mode
│
└── fixtures/
    └── workflow_helpers.py                      # Shared utilities
```

---

## Test Specifications

### Workflow 1: Root Cause Hunting

#### Test 1.1: `test_trace_tool_failure_to_decision` (Happy Path)

**Scenario**: Developer sees a tool failure, wants to find the decision that caused it.

**Setup**:
- Session with: LLM request → decision → tool call → tool failure
- Decision has clear reasoning and evidence chain

**Steps**:
1. Load session from cassette
2. Find tool_result event with error
3. Trace upstream_event_ids backward to decision
4. Verify decision has reasoning, evidence, and links to failure

**Assertions**:
```python
assert failure.event_type == "tool_result"
assert failure.error is not None
assert decision.event_type == "decision"
assert failure.id in decision.upstream_event_ids or tool_call.id in decision.upstream_event_ids
assert decision.reasoning is not None
assert len(decision.evidence) > 0
```

#### Test 1.2: `test_find_evidence_chain_for_hallucination` (Failure Mode)

**Scenario**: Agent made a decision based on hallucinated evidence. Developer needs to find where evidence went wrong.

**Setup**:
- Session with: tool call → tool result → decision with fabricated evidence
- Decision's evidence_event_ids don't match actual tool results

**Steps**:
1. Load session from cassette
2. Find decision event
3. Verify evidence chain is broken (evidence_event_ids reference non-existent or inconsistent data)
4. Assert debugger surfaces the gap

**Assertions**:
```python
decision = find_event(session, event_type="decision")
for evidence_id in decision.evidence_event_ids:
    evidence_event = get_event_by_id(session, evidence_id)
    # Evidence should exist and match decision's claims
    assert evidence_event is not None
    assert evidence_matches_decision(evidence_event, decision)
```

---

### Workflow 2: Safety Auditing

#### Test 2.1: `test_enumerate_all_safety_events` (Happy Path)

**Scenario**: Developer wants to see all safety-relevant events in a session.

**Setup**:
- Session with: multiple safety_check events (pass/warn/block), policy_violation, refusal

**Steps**:
1. Load session from cassette
2. Query for all safety_check events
3. Query for all policy_violation events
4. Query for all refusal events
5. Verify all are captured with required fields

**Assertions**:
```python
safety_checks = filter_events(session, event_type="safety_check")
violations = filter_events(session, event_type="policy_violation")
refusals = filter_events(session, event_type="refusal")

assert len(safety_checks) >= 2
assert len(violations) >= 1
assert len(refusals) >= 1

for sc in safety_checks:
    assert sc.outcome in ["pass", "warn", "block"]
    assert sc.risk_level is not None

for v in violations:
    assert v.severity is not None
    assert v.violation_type is not None
```

#### Test 2.2: `test_detect_missed_policy_violation` (Failure Mode)

**Scenario**: Agent did something dangerous but no policy_violation was recorded. Developer audits to find the gap.

**Setup**:
- Session with: safety_check that should have blocked but passed
- downstream event shows dangerous action occurred

**Steps**:
1. Load session from cassette
2. Find safety_check with outcome="pass" but high risk_level
3. Find downstream event that shows the risk materialized
4. Verify the gap is visible in the trace

**Assertions**:
```python
risky_passes = [sc for sc in safety_checks
                if sc.outcome == "pass" and sc.risk_level == "high"]
assert len(risky_passes) >= 1

# Find evidence the risk materialized
dangerous_event = find_downstream_danger(session, risky_passes[0])
assert dangerous_event is not None
```

---

### Workflow 3: Reproducibility

#### Test 3.1: `test_replay_from_checkpoint_same_output` (Happy Path)

**Scenario**: Developer replays a session from a checkpoint and expects identical output.

**Setup**:
- Session with checkpoint mid-way
- Events before checkpoint, events after checkpoint

**Steps**:
1. Load session from cassette
2. Find checkpoint event
3. Simulate replay from checkpoint
4. Verify events after checkpoint are reproducible with same inputs

**Assertions**:
```python
checkpoint = find_checkpoint(session)
assert checkpoint is not None
assert checkpoint.importance >= 0.5

# Replay should produce same event sequence
replay_events = replay_from_checkpoint(session, checkpoint)
original_events = events_after_checkpoint(session, checkpoint)

for replay, original in zip(replay_events, original_events):
    assert replay.event_type == original.event_type
    # Content may differ (LLM), but structure should match
```

#### Test 3.2: `test_diff_two_sessions_find_divergence` (Failure Mode)

**Scenario**: Same agent, two runs. One succeeded, one failed. Developer needs to find where they diverged.

**Setup**:
- Two sessions from same agent/prompts
- One succeeds, one fails at some point
- First divergence point is identifiable

**Steps**:
1. Load both sessions from cassettes
2. Compare events pairwise
3. Find first event that differs
4. Verify divergence point is clearly identifiable

**Assertions**:
```python
session_a = load_session("success.yaml")
session_b = load_session("failure.yaml")

divergence = find_first_divergence(session_a, session_b)
assert divergence is not None
assert divergence.event_a is not None
assert divergence.event_b is not None
assert divergence.index is not None

# Divergence should explain why outcomes differ
assert divergence.explanation is not None
```

---

## Cassette Format

Each cassette is a YAML file capturing:

```yaml
name: tool_failure_to_decision
recorded_at: 2026-03-25T10:00:00Z
framework: langchain  # or pydantic_ai, crewai, etc.

interactions:
  - id: llm-request-1
    type: llm_request
    request:
      model: gpt-4
      messages:
        - role: user
          content: "What is the capital of France?"
      temperature: 0.7
    response:
      content: "The capital of France is Paris."
      usage:
        input_tokens: 15
        output_tokens: 8
      finish_reason: stop
      request_id: req_abc123

  - id: tool-call-1
    type: tool_call
    request:
      tool_name: search
      arguments:
        query: "Paris population"
    response:
      result:
        population: "2.1 million"
        source: "wikipedia"
      duration_ms: 150
```

---

## Recording Workflow

### Command to Record New Cassette

```bash
# Record a new cassette (runs real agent, captures LLM calls)
make record-test WORKFLOW=root_cause SCENARIO=tool_failure_to_decision

# Or manually:
python scripts/record_cassette.py \
  --workflow root_cause \
  --scenario tool_failure_to_decision \
  --framework langchain
```

### Recording Script Requirements

1. Load real framework (LangChain, Pydantic AI, etc.)
2. Run agent with SDK patched
3. Capture all HTTP interactions (LLM API calls)
4. Save to YAML cassette
5. Include metadata (timestamp, framework, SDK version)

### CI Replay

```bash
# CI runs tests with cassettes (no real API calls)
pytest tests/workflows/ -v
```

---

## Implementation Phases

### Phase 1: Infrastructure
- Create `tests/workflows/` directory structure
- Create `tests/cassettes/` directory structure
- Implement cassette recording script
- Implement cassette replay fixture

### Phase 2: Workflow Tests
- Implement `test_root_cause_hunting.py`
- Implement `test_safety_auditing.py`
- Implement `test_reproducibility.py`

### Phase 3: Cassettes
- Record cassettes for each test
- Verify CI runs pass with cassettes

### Phase 4: Documentation
- Update CLAUDE.md with workflow testing guide
- Document how to record new cassettes
- Document how to refresh stale cassettes

---

## Success Criteria

1. **All 6 tests pass in CI** - No flakiness, fully deterministic
2. **Tests verify workflows, not just events** - Each test exercises a debugging flow
3. **Cassettes are maintainable** - Clear format, easy to refresh
4. **Recording workflow is documented** - Any developer can add new cassettes
5. **Tests catch real bugs** - When SDK breaks workflow support, tests fail

---

## Open Questions

1. **Which framework for initial cassettes?** Start with LangChain (most popular) or Pydantic AI (cleaner API)?
   - Recommendation: Start with Pydantic AI for cleaner recordings

2. **How often to refresh cassettes?** Monthly, quarterly, or on-demand?
   - Recommendation: On-demand when tests fail, or quarterly as maintenance

3. **Should cassettes be committed?** Yes (for CI), or stored externally?
   - Recommendation: Commit to repo for simplicity

---

## References

- [Real-World Agent Failure Patterns](../../REAL_WORLD_AGENT_FAILURE_PATTERNS.md)
- [Current Benchmark Tests](../../../tests/test_benchmarks.py)
- [SDK Documentation](../../../agent_debugger_sdk/)

