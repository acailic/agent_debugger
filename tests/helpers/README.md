# Test Helpers and Utilities

This directory contains shared testing utilities organized by purpose.

## Available Modules

### `fakes.py` - Fake Implementations for Unit Tests

**Purpose**: Lightweight in-memory implementations that satisfy production interfaces for isolated unit testing.

**When to use**:
- Writing unit tests that need to test interaction with SDK components
- Tests that need deterministic behavior without external dependencies
- Tests that need to verify method calls and state changes

**Available fakes**:
- `FakeEventBuffer`: In-memory event buffer that records all publish calls and supports subscriber queues
- `FakeTraceIntelligence`: Returns deterministic analysis results and records all method calls
- `FakeRedactionPipeline`: Records calls and returns events unchanged

**Example**:
```python
from tests.helpers.fakes import FakeEventBuffer, FakeTraceIntelligence

buffer = FakeEventBuffer()
intel = FakeTraceIntelligence(replay_value=0.75)

# Use in tests
await buffer.publish("session-123", event)
assert len(buffer.published) == 1
```

**Used in**:
- `tests/test_services_unit.py` - API service unit tests
- `tests/test_buffer_fakes.py` - Buffer fake implementation tests

---

### `workflow_helpers.py` - Cassette and Workflow Test Utilities

**Location**: `tests/fixtures/workflow_helpers.py`

**Purpose**: Helper functions for loading YAML cassettes and querying event collections in workflow-based tests.

**When to use**:
- Writing tests that use recorded cassette data from `tests/cassettes/`
- Tests that need to query/filter events by type or ID
- Tests that validate evidence chains, safety checks, or reproducibility

**Available helpers**:

#### Cassette Loading
- `load_cassette(path)` - Load a YAML cassette and return raw interaction dicts
- `cassette_events(interactions, session_id)` - Convert cassette interactions into typed TraceEvent instances

#### Event Querying
- `find_event(events, *, event_type, index=0)` - Find the nth event of a given type
- `filter_events(events, *, event_type)` - Return all events matching a type
- `get_event_by_id(events, event_id)` - Look up an event by its ID

#### Root Cause Analysis
- `validate_evidence_chain(decision, events)` - Validate decision evidence chains (existence, temporal, content)
- `EvidenceIssue` - Dataclass describing problems found in evidence chains

#### Safety Analysis
- `find_risky_passes(events)` - Find safety checks that passed despite high risk
- `find_downstream_danger(events, safety_event)` - Find downstream events that materialized a risk

#### Reproducibility
- `find_first_divergence(events_a, events_b)` - Find the first point where two sessions diverge
- `Divergence` - Dataclass representing a divergence point

**Example**:
```python
from tests.fixtures.workflow_helpers import load_cassette, cassette_events, find_event

# Load and convert cassette
interactions = load_cassette("safety/enumerate_safety_events.yaml")
events = cassette_events(interactions)

# Query events
checkpoint = find_event(events, event_type=EventType.CHECKPOINT)
```

**Used in**:
- `tests/workflows/test_reproducibility.py` - Reproducibility and diff tests
- `tests/workflows/test_safety_auditing.py` - Safety analysis tests
- `tests/workflows/test_root_cause_hunting.py` - Evidence chain validation tests
- `tests/workflows/conftest.py` - Workflow test fixtures

---

## Choosing the Right Helper

| Need | Use |
|------|-----|
| Unit test with deterministic behavior | `fakes.py` |
| Test with recorded cassette data | `workflow_helpers.py` |
| Verify method calls/invocations | `fakes.py` (fake classes record calls) |
| Query/filter event collections | `workflow_helpers.py` |
| Validate evidence chains | `workflow_helpers.py` |
| Test safety/risk patterns | `workflow_helpers.py` |

---

## Adding New Helpers

When adding new test utilities:

1. **Choose the right location**:
   - Fake implementations → `helpers/fakes.py`
   - Cassette/workflow helpers → `fixtures/workflow_helpers.py`
   - General-purpose helpers → Create a new file in `helpers/`

2. **Document usage**:
   - Add docstrings with examples
   - Update this README with the new helper

3. **Follow conventions**:
   - Use type hints
   - Keep helpers focused and single-purpose
   - Avoid test-specific logic in shared helpers
