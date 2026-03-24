# Test Strategy Design: No-Brainer Features

**Date**: 2026-03-24
**Status**: Approved
**Scope**: Comprehensive test coverage for 5 No-Brainer Features

---

## Executive Summary

This design specifies a comprehensive test strategy for the 5 No-Brainer Features:
1. "Why Did It Fail?" Button
2. Failure Memory Search
3. Smart Replay Highlights
4. Behavior Change Alerts
5. Natural Language Debugging

**Approach**: Feature-by-feature systematic testing with ~10-12 tests per feature.
**Total Tests**: 57 tests across 5 files
**External Dependencies**: All mocked (ChromaDB, sentence-transformers, LLM APIs)

---

## Goals

1. **Comprehensive coverage**: 8-12 tests per feature covering happy path, edge cases, and error handling
2. **Fast CI**: All external dependencies mocked for deterministic, fast tests
3. **Clear organization**: One file per feature for maintainability
4. **Consistent patterns**: Shared fixtures and test structure across all files

---

## File Structure

```
tests/
├── test_feature_1_why_button.py       # ~200 lines, 10 tests
├── test_feature_2_failure_memory.py   # ~220 lines, 12 tests
├── test_feature_3_smart_replay.py     # ~180 lines, 10 tests
├── test_feature_4_behavior_alerts.py  # ~200 lines, 11 tests
├── test_feature_5_nl_debugging.py     # ~200 lines, 11 tests
└── conftest_no_brainery.py            # ~100 lines (shared fixtures)
```

**Total**: ~1,100 lines, 57 tests

---

## Shared Fixtures (conftest_no_brainery.py)

### Event Factories

```python
@pytest.fixture
def make_error_event():
    """Factory for creating ErrorEvent instances."""
    def _make(id, error_type="ValueError", message="Test error", **kwargs):
        from agent_debugger_sdk.core.events import ErrorEvent
        return ErrorEvent(
            id=id,
            session_id=kwargs.get("session_id", "test-session"),
            error_type=error_type,
            error_message=message,
            timestamp=kwargs.get("timestamp", datetime.now(timezone.utc)),
            parent_id=kwargs.get("parent_id"),
        )
    return _make

@pytest.fixture
def make_decision_event():
    """Factory for creating DecisionEvent instances."""
    def _make(id, action="proceed", confidence=0.9, **kwargs):
        from agent_debugger_sdk.core.events import DecisionEvent
        return DecisionEvent(
            id=id,
            session_id=kwargs.get("session_id", "test-session"),
            chosen_action=action,
            confidence=confidence,
            evidence=kwargs.get("evidence", []),
            parent_id=kwargs.get("parent_id"),
        )
    return _make

@pytest.fixture
def make_session():
    """Factory for creating Session instances."""
    def _make(events, session_id="test-session", **kwargs):
        from agent_debugger_sdk.core.events import Session
        return Session(
            id=session_id,
            agent_name=kwargs.get("agent_name", "test-agent"),
            framework=kwargs.get("framework", "test"),
            events=events,
        )
    return _make
```

### Mock Factories

```python
@pytest.fixture
def mock_embedding_model():
    """Mock sentence-transformers model."""
    with patch("sentence_transformers.SentenceTransformer") as mock:
        instance = MagicMock()
        instance.encode.return_value = [0.1] * 384  # Dummy embedding
        mock.return_value = instance
        yield instance

@pytest.fixture
def mock_vector_db():
    """Mock ChromaDB client."""
    with patch("chromadb.Client") as mock:
        instance = MagicMock()
        instance.query.return_value = {"ids": [["id1"]], "distances": [[0.1]]}
        mock.return_value = instance
        yield instance

@pytest.fixture
def mock_llm_client():
    """Mock LLM API client."""
    mock = AsyncMock()
    mock.generate = AsyncMock(return_value="Test LLM response")
    return mock
```

---

## Feature 1: "Why Did It Fail?" Button Tests

**File**: `tests/test_feature_1_why_button.py`

### Test Classes

| Class | Count | Purpose |
|-------|-------|---------|
| `TestWhyButtonHappyPath` | 4 | Causal tracing, root cause ranking, explanation generation |
| `TestWhyButtonEdgeCases` | 4 | No parents, multiple errors, disconnected events, low confidence |
| `TestWhyButtonErrorHandling` | 2 | Missing events, corrupted data, circular chains |

### Key Test Cases

```python
class TestWhyButtonHappyPath:
    def test_explain_single_error_returns_root_cause(self, explainer, make_error_event)
    def test_explain_returns_confidence_score(self, explainer, make_error_event)
    def test_explain_includes_evidence_links(self, explainer, make_error_event, make_session)
    def test_trace_causal_chain_follows_parent_ids(self, explainer, make_error_event, make_decision_event)

class TestWhyButtonEdgeCases:
    def test_no_parent_chain_returns_self_as_cause(self, explainer, make_error_event)
    def test_multiple_errors_ranks_by_likelihood(self, explainer, make_error_event)
    def test_disconnected_events_ignored(self, explainer, make_error_event, make_decision_event)
    def test_low_confidence_decision_flagged(self, explainer, make_error_event, make_decision_event)

class TestWhyButtonErrorHandling:
    def test_missing_event_id_raises_not_found(self, explainer)
    def test_corrupted_event_handled_gracefully(self, explainer)
    def test_circular_parent_chain_detected(self, explainer, make_error_event)
```

---

## Feature 2: Failure Memory Search Tests

**File**: `tests/test_feature_2_failure_memory.py`

### Test Classes

| Class | Count | Purpose |
|-------|-------|---------|
| `TestFailureMemoryHappyPath` | 4 | Store failures, search similar, retrieve solutions |
| `TestFailureMemoryEdgeCases` | 4 | Empty memory, low similarity, duplicates, no errors |
| `TestFailureMemoryErrorHandling` | 3 | Embedding failure, DB unavailable, malformed metadata |
| `TestFailureMemoryIntegration` | 1 | Integration with Why button |

### Key Test Cases

```python
class TestFailureMemoryHappyPath:
    def test_remember_failure_stores_embedding(self, memory, make_session, make_error_event)
    def test_search_similar_returns_matches(self, memory, mock_vector_db)
    def test_search_includes_fix_information(self, memory, mock_vector_db)
    def test_failure_signature_extracts_key_fields(self, memory, make_session, make_error_event)

class TestFailureMemoryEdgeCases:
    def test_empty_memory_returns_empty_list(self, memory, mock_vector_db)
    def test_low_similarity_excluded(self, memory, mock_vector_db)
    def test_duplicate_failures_update_existing(self, memory, mock_vector_db, make_session, make_error_event)
    def test_session_without_error_skipped(self, memory, make_session, make_decision_event)

class TestFailureMemoryErrorHandling:
    def test_embedding_failure_returns_graceful_error(self, memory, mock_embedding_model)
    def test_vector_db_unavailable_returns_empty(self, memory, mock_vector_db)
    def test_malformed_metadata_handled(self, memory, mock_vector_db)
```

---

## Feature 3: Smart Replay Highlights Tests

**File**: `tests/test_feature_3_smart_replay.py`

### Test Classes

| Class | Count | Purpose |
|-------|-------|---------|
| `TestSmartReplayHappyPath` | 5 | Importance scoring, segment generation, highlight curation |
| `TestSmartReplayEdgeCases` | 4 | Empty sessions, all low/high importance, overlapping segments |
| `TestSmartReplayErrorHandling` | 2 | Malformed events, missing context |
| `TestSmartReplayScoringRules` | 4 | Specific scoring rules per event type |

### Key Test Cases

```python
class TestSmartReplayHappyPath:
    def test_generate_highlights_returns_key_moments(self, replay, make_session, make_error_event)
    def test_score_importance_errors_high(self, replay, make_error_event)
    def test_score_importance_low_confidence_medium(self, replay, make_decision_event)
    def test_score_importance_routine_low(self, replay, make_session)
    def test_create_segments_includes_context(self, replay, make_error_event, make_decision_event, make_session)

class TestSmartReplayEdgeCases:
    def test_empty_session_returns_empty_highlights(self, replay, make_session)
    def test_all_low_importance_returns_top_n(self, replay, make_session, make_decision_event)
    def test_all_high_importance_prioritizes_by_score(self, replay, make_session, make_error_event)
    def test_overlapping_segments_merged(self, replay, make_session, make_error_event, make_decision_event)

class TestSmartReplayScoringRules:
    def test_refusal_high_importance(self, replay)
    def test_safety_check_medium_importance(self, replay)
    def test_behavior_alert_high_importance(self, replay)
```

---

## Feature 4: Behavior Change Alerts Tests

**File**: `tests/test_feature_4_behavior_alerts.py`

### Test Classes

| Class | Count | Purpose |
|-------|-------|---------|
| `TestBehaviorAlertsHappyPath` | 5 | Baseline calculation, drift detection, root cause ID |
| `TestBehaviorAlertsEdgeCases` | 4 | Insufficient data, no changes, multiple changes, gradual drift |
| `TestBehaviorAlertsErrorHandling` | 3 | Missing metrics, malformed data, partial results |
| `TestBehaviorAlertsThresholds` | 3 | Specific threshold values (2x, 50%, 2x) |

### Key Test Cases

```python
class TestBehaviorAlertsHappyPath:
    def test_detect_changes_finds_decision_pattern_shift(self, monitor, baseline_data)
    def test_detect_changes_finds_latency_increase(self, monitor, baseline_data)
    def test_detect_changes_finds_failure_rate_spike(self, monitor, baseline_data)
    def test_identify_root_cause_finds_config_change(self, monitor, baseline_data)
    def test_alert_includes_before_after_values(self, monitor, baseline_data)

class TestBehaviorAlertsEdgeCases:
    def test_insufficient_baseline_returns_no_alerts(self, monitor)
    def test_no_significant_changes_returns_empty(self, monitor)
    def test_multiple_simultaneous_changes_all_detected(self, monitor)
    def test_gradual_drift_below_threshold_not_flagged(self, monitor)

class TestBehaviorAlertsThresholds:
    def test_failure_rate_threshold_is_2x(self, monitor)
    def test_latency_threshold_is_50_percent(self, monitor)
    def test_cost_threshold_is_2x(self, monitor)
```

---

## Feature 5: Natural Language Debugging Tests

**File**: `tests/test_feature_5_nl_debugging.py`

### Test Classes

| Class | Count | Purpose |
|-------|-------|---------|
| `TestNLDebuggingHappyPath` | 5 | Intent parsing, context gathering, answer generation |
| `TestNLDebuggingEdgeCases` | 4 | Ambiguous queries, empty sessions, no relevant events |
| `TestNLDebuggingErrorHandling` | 3 | LLM timeout, API errors, malformed responses |
| `TestNLDebuggingQueryTypes` | 3 | Specific query type handling (fix, similar, explain) |

### Key Test Cases

```python
class TestNLDebuggingHappyPath:
    def test_answer_query_returns_natural_language(self, debugger, make_session, make_error_event)
    def test_parse_intent_extracts_why_failure(self, debugger)
    def test_parse_intent_extracts_what_changed(self, debugger)
    def test_gather_context_includes_relevant_events(self, debugger, make_session, make_error_event)
    def test_answer_includes_evidence_links(self, debugger, make_session, make_error_event)

class TestNLDebuggingEdgeCases:
    def test_ambiguous_query_requests_clarification(self, debugger, make_session)
    def test_empty_session_returns_no_data_message(self, debugger, make_session)
    def test_no_relevant_events_returns_not_found(self, debugger, make_session, make_decision_event)
    def test_multi_part_query_handles_all_parts(self, debugger, make_session, make_error_event)

class TestNLDebuggingErrorHandling:
    def test_llm_timeout_returns_fallback(self, debugger, make_session, make_error_event)
    def test_llm_error_returns_error_message(self, debugger, make_session)
    def test_malformed_llm_response_handled(self, debugger, make_session, mock_llm_client)

class TestNLDebuggingQueryTypes:
    def test_how_to_fix_query(self, debugger, make_session, make_error_event)
    def test_similar_failures_query(self, debugger, make_session, make_error_event)
    def test_explain_decision_query(self, debugger, make_session, make_decision_event)
```

---

## Coverage Summary

| Feature | Happy Path | Edge Cases | Error Handling | Total |
|---------|------------|------------|----------------|-------|
| 1. Why Button | 4 | 4 | 2 | 10 |
| 2. Failure Memory | 4 | 4 | 3 | 11 |
| 3. Smart Replay | 5 | 4 | 3 | 12 |
| 4. Behavior Alerts | 5 | 4 | 3 | 12 |
| 5. NL Debugging | 5 | 4 | 3 | 12 |
| **Total** | **23** | **20** | **14** | **57** |

---

## Key Design Decisions

1. **Mock everything**: All external dependencies (ChromaDB, sentence-transformers, LLM APIs) are mocked for fast, deterministic CI
2. **One file per feature**: Clear ownership, easy to find tests, consistent with existing structure
3. **Shared fixtures**: `conftest_no_brainery.py` provides reusable event factories and mocks
4. **Consistent class structure**: `HappyPath`, `EdgeCases`, `ErrorHandling` pattern across all files
5. **Async support**: NL debugging tests use `pytest.mark.asyncio` for async methods

---

## Dependencies

- **pytest**: Test framework
- **pytest-asyncio**: Async test support
- **unittest.mock**: Mocking utilities
- No external service dependencies (all mocked)

---

## Success Criteria

1. All 57 tests pass
2. No external service calls in CI
3. Test execution time < 30 seconds total
4. Code coverage > 80% for new feature modules
5. All tests follow consistent naming and structure
