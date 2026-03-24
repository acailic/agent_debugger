# Test Strategy Design: Comprehensive Test Suite Overhaul

**Date**: 2026-03-24
**Status**: Draft
**Approach**: Comprehensive (Recommended)
**Priority Areas**: SDK events package, CI regression tests

## Executive Summary

This design specifies a comprehensive test strategy to make the codebase more robust and professional. The strategy addresses:
- Fixing syntax errors in existing test files
- Complete test coverage for new features (adaptive intelligence, benchmarks, L3 replay)
- Adding SDK events package tests
- Adding CI regression tests

## Goals

1. **Fix blocking issues**: `test_replay_depth_l3.py` has syntax errors
2. **Complete coverage**: All new features have comprehensive tests
3. **Add regression tests**: CI catches regressions early
4. **Professional quality**: Well-organized, maintainable, documented

## Scope

### Section 1: SDK Events Package Tests

**What**: Comprehensive tests for `agent_debugger_sdk/core/events/` package

**Coverage**:
- All 13 event types with specific field validation
- EventType registry lazy loading
- Event serialization/deserialization round-trips
- Pydantic validation behavior
- Event inheritance patterns

**File**: `tests/test_events_package.py` (~400 lines)

**Test Classes**:
- `TestEventTypeRegistry` - Registry completeness, lazy loading, class mapping
- `TestEventTypes` - All event types (ToolCall, ToolResult, LLMRequest, LLMResponse, Decision, SafetyCheck, Refusal, PolicyViolation, PromptPolicy, AgentTurn, BehaviorAlert, Error)
- `TestEventSerialization` - JSON serialization, round-trip validation
- `TestEventHierarchy` - Inheritance from TraceEvent base class

### Section 2: Replay Depth L3 Tests (Fix)

**What**: Fix syntax errors and complete coverage for L3+ replay features

**Current Issues**:
- Line 31: Missing `from` in import statement
- Lines 31-37: Indentation errors
- Line 51-57: Incomplete fixture definition
- Missing imports for `TraceContext`, checkpoint classes
- Some test methods are incomplete

**File**: `tests/test_replay_depth_l3.py` (~150 lines added, ~100 lines fixed)

**Test Classes**:
- `TestDeterministicRestoreHooks` - LangChain restore, custom restore, fallback behavior
- `TestStateDriftDetection` - Identical states, different messages, severity levels
- `TestAutoReplay` - Event replay, filtering, importance thresholds
- `TestCachedResponseReplay` - Cache store/retrieve, deterministic replay, hash consistency

### Section 3: Adaptive Intelligence & Benchmark Tests (Complete)

**What**: Add edge cases and improve coverage for existing test files

**Files**:
- `tests/test_adaptive_intelligence.py` (~200 lines added)
- `tests/test_benchmarks.py` (~100 lines added)

**Test Classes**:
- `TestCrossSessionClustering` - Cluster similar failures, representative selection
- `TestRetryChurnDetection` - Tool loop detection, churn indicators
- `TestLatencySpikeDetection` - Slow operations, replay value impact
- `TestPolicyEscalationTracking` - Policy shifts, escalation chains
- `TestRepresentativeTraceSelection` - One representative per cluster
- `TestRetentionTierAssignment` - Tier thresholds, edge cases

### Section 4: CI Regression Tests

**What**: Regression tests to catch regressions early in CI

**File**: `tests/test_regressions.py` (~150 lines)

**Coverage**:
- Critical flows from demo scripts
- Known issue patterns (e.g., import cycles, serialization)
- API contract validation
- Event ordering guarantees

**Test Cases**:
- `test_sdk_imports_work` - Basic SDK import doesn't fail
- `test_session_creation_round_trip` - Session can be created and retrieved
- `test_event_serialization_json` - Events serialize to JSON correctly
- `test_api_health_endpoint` - Health check returns 200
- `test_tenant_isolation_basic` - Tenant data isolation works

## Non-Goals

- Frontend tests (out of scope)
- Performance benchmarks (separate effort)
- Full E2E tests (covered by existing `test_e2e_*.py`)

## Implementation Notes

### Test Utilities

Create shared fixtures and builders:
- `tests/fixtures/events.py` - Event builder factory
- `tests/fixtures/sessions.py` - Session builder factory

### Mock Patterns

Standardize mocking approach:
- Use `unittest.mock` for sync, `AsyncMock` for async
- Avoid patching where possible, prefer dependency injection
- Clear mocks between tests

### CI Integration

Regression tests run on every PR:
- Added to `.github/workflows/ci.yml`
- Must pass before merge
- Fast execution (< 30 seconds total)

## Success Criteria

1. **All syntax errors fixed** - `python -m py_compile` passes
2. **All tests pass** - `pytest` exits 0
3. **Coverage improved** - New files have >80% coverage
4. **CI green** - Regression tests pass in CI
5. **Professional quality** - Code review approves

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_events_package.py` | New | ~400 |
| `tests/test_replay_depth_l3.py` | Fix | ~250 (net) |
| `tests/test_adaptive_intelligence.py` | Expand | +200 |
| `tests/test_benchmarks.py` | Expand | +100 |
| `tests/test_regressions.py` | New | ~150 |

**Total**: ~1,100 lines added/fixed across 5 files

## Timeline

- Section 1 (SDK Events): ~1 hour
- Section 2 (L3 Replay Fix): ~1 hour
- Section 3 (Adaptive/Benchmarks): ~1 hour
- Section 4 (Regressions): ~30 minutes

**Total**: ~3.5 hours

## Dependencies

- No external dependencies
- Uses existing pytest fixtures
- Compatible with Python 3.10+
