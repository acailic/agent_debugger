# Testing & Coverage Improvement Plan

**Current Status: 90% coverage (420 passing, 1 failing)**  
**Goal: 95%+ coverage with all tests passing**

## 🎯 Executive Summary

Our test suite is in good shape with 90% coverage, but we have opportunities to:
1. **Fix the failing test** (package version mismatch)
2. **Increase coverage** in low-coverage modules
3. **Learn from testing** to identify potential bugs
4. **Add edge case tests** for robustness

---

## 📊 Coverage Analysis by Priority

### Priority 1: Critical Low Coverage (< 75%)

| Module | Coverage | Missing Lines | Impact |
|--------|----------|---------------|---------|
| `benchmarks/seed_data.py` | **57%** | 46 lines | Demo/benchmark functionality |
| `api/replay_routes.py` | **69%** | 11 lines | Core API endpoints |
| `agent_debugger_sdk/auto_patch/adapters/langchain_adapter.py` | **71%** | 45 lines | Critical adapter |

### Priority 2: Medium Coverage (75-85%)

| Module | Coverage | Missing Lines | Impact |
|--------|----------|---------------|---------|
| `api/ui_routes.py` | **73%** | 3 lines | UI endpoints |
| `agent_debugger_sdk/auto_patch/adapters/crewai_adapter.py` | **80%** | 20 lines | Adapter support |
| `agent_debugger_sdk/auto_patch/adapters/llamaindex_adapter.py` | **81%** | 20 lines | Adapter support |
| `redaction/pipeline.py` | **83%** | 25 lines | Data security |

### Priority 3: Good Coverage (85-95%)

| Module | Coverage | Missing Lines | Impact |
|--------|----------|---------------|---------|
| `agent_debugger_sdk/auto_patch/adapters/autogen_adapter.py` | **85%** | 22 lines | Adapter support |
| `agent_debugger_sdk/checkpoints/validation.py` | **86%** | 5 lines | Checkpoint integrity |
| `agent_debugger_sdk/auto_patch/adapters/openai_adapter.py` | **87%** | 14 lines | Primary adapter |
| `agent_debugger_sdk/auto_patch/adapters/anthropic_adapter.py` | **88%** | 12 lines | Primary adapter |

---

## 🐛 Issues Discovered Through Testing

### Issue 1: Package Version Test Failure

**Test:** `tests/test_package.py::test_version_exists`  
**Problem:** Looking for package "peaky-peek" which doesn't exist  
**Root Cause:** The package name in metadata doesn't match expected name

```python
# Current failing code:
assert agent_debugger_sdk.__version__ == version("peaky-peek")
```

**Fix Required:**
1. Check actual package name in `pyproject.toml`
2. Update test to use correct package name or mock the version check

---

## 📋 Testing Improvements Checklist

### Phase 1: Fix Failing Tests ⚠️

- [ ] **Fix package version test**
  - File: `tests/test_package.py`
  - Action: Verify package name in `pyproject.toml` and update test
  - Expected: Test passes with correct package name

### Phase 2: Critical Coverage Gaps 🔴

#### 2.1 API Routes Testing (api/replay_routes.py - 69% → 90%)

- [ ] **Add tests for replay endpoint edge cases**
  - Missing lines: 80, 99-121
  - Test scenarios:
    - Replay with invalid session ID
    - Replay with missing checkpoints
    - Replay with corrupted data
    - Concurrent replay requests

#### 2.2 LangChain Adapter Testing (71% → 85%)

- [ ] **Test callback handler edge cases**
  - Missing lines: 90-91, 109-111, 134-135, 164, 173-174, 178, 182, 189, 192, 195, 198, 201, 204, 207
  - Test scenarios:
    - Error handling in callbacks
    - Multiple concurrent handlers
    - Handler installation/removal race conditions
    - Missing or malformed data in callbacks

- [ ] **Test adapter lifecycle**
  - Missing lines: 284-295, 308-323
  - Test scenarios:
    - Patch/unpatch idempotency
    - Handler cleanup on errors
    - Multiple patch attempts

#### 2.3 Benchmarks/Seed Data (57% → 80%)

- [ ] **Add tests for seed scenarios**
  - Missing lines: Multiple functions partially covered
  - Note: This is lower priority as it's primarily for demos
  - Consider marking as test-only code if not critical

### Phase 3: Medium Priority Coverage 🟡

#### 3.1 Redaction Pipeline (83% → 95%)

- [ ] **Test edge cases in redaction**
  - Missing lines: 66, 94-96, 126, 130, 137, 147-157, 169, 192-203, 209, 219
  - Test scenarios:
    - Malformed input data
    - Nested sensitive data
    - Custom redaction patterns
    - Performance with large payloads
    - **Security-critical**: Ensure all paths properly redact sensitive data

#### 3.2 UI Routes (73% → 90%)

- [ ] **Test UI endpoint variations**
  - Missing lines: 17-19
  - Simple to add, quick win

#### 3.3 Adapter Coverage Improvements

- [ ] **CrewAI Adapter** (80% → 90%)
  - Missing error paths and edge cases
  
- [ ] **LlamaIndex Adapter** (81% → 90%)
  - Missing error paths and edge cases

- [ ] **AutoGen Adapter** (85% → 90%)
  - Missing error paths and edge cases

### Phase 4: Low Priority / Nice to Have 🟢

- [ ] **Checkpoint Validation** (86% → 95%)
- [ ] **OpenAI Adapter** (87% → 95%)
- [ ] **Anthropic Adapter** (88% → 95%)

---

## 🔍 Testing Insights & Potential Bugs

### Potential Bug 1: Error Handling in Redaction Pipeline

**Location:** `redaction/pipeline.py:147-157`  
**Issue:** Uncovered error handling paths might indicate insufficient error testing  
**Risk:** HIGH - Security-critical functionality  
**Action:** Add comprehensive error case tests

### Potential Bug 2: LangChain Callback Edge Cases

**Location:** `langchain_adapter.py:284-295, 308-323`  
**Issue:** Handler installation/removal paths untested  
**Risk:** MEDIUM - Could cause resource leaks or race conditions  
**Action:** Test handler lifecycle thoroughly

### Potential Bug 3: API Replay Error Paths

**Location:** `api/replay_routes.py:99-121`  
**Issue:** Error paths not covered  
**Risk:** MEDIUM - Could expose poor error messages or unhandled exceptions  
**Action:** Test all error scenarios

---

## 🛠️ Implementation Strategy

### Week 1: Fix & Foundation
1. Fix failing version test
2. Add critical API route tests
3. Add redaction security tests

### Week 2: Adapter Coverage
1. LangChain adapter comprehensive tests
2. CrewAI and LlamaIndex adapter tests
3. AutoGen adapter tests

### Week 3: Polish & Edge Cases
1. Remaining adapter improvements
2. UI routes tests
3. Benchmark seed data (if needed)

### Week 4: Review & Refine
1. Review all new tests for quality
2. Add missing edge cases
3. Update documentation
4. Target: 95%+ coverage

---

## 📈 Success Metrics

- [ ] All tests passing (currently 1 failing)
- [ ] Overall coverage ≥ 95% (currently 90%)
- [ ] No module with coverage < 80%
- [ ] All security-critical paths tested
- [ ] All error paths covered
- [ ] Edge cases documented

---

## 🎓 Testing Best Practices to Apply

1. **Test Behavior, Not Implementation**
   - Focus on what the code should do, not how
   - Use property-based testing for edge cases

2. **Test Error Paths Explicitly**
   - Every exception handler should have tests
   - Test invalid inputs and boundary conditions

3. **Security-First Testing**
   - Prioritize redaction and auth code
   - Test for injection attacks and malformed data

4. **Integration vs Unit Tests**
   - Unit tests for logic isolation
   - Integration tests for adapter interactions

5. **Coverage != Quality**
   - High coverage doesn't mean good tests
   - Review test assertions and scenarios

---

## 🚀 Quick Wins (Do First)

1. **Fix version test** - 5 minutes
2. **UI routes tests** - 15 minutes  
3. **API replay error tests** - 30 minutes
4. **Redaction edge cases** - 1 hour

These will get us to ~92% coverage quickly!

---

## 📝 Notes

- `test_integration.py` and `test_research_workflows.py` show 0% coverage but these are test files themselves
- Consider excluding them from coverage reporting
- 41 files already have 100% coverage - great job! 🎉
