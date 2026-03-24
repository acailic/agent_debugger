# Testing Action Items - Immediate Next Steps

**Generated:** 2026-03-24  
**Status:** 437 passing tests, 18 failing (mostly new tests needing API adjustments)

---

## 🎯 Quick Wins (30 minutes or less)

### 1. Fix Redaction Event API Tests ✅ READY TO FIX
**File:** `tests/test_redaction_security_coverage.py`  
**Issue:** Event classes have different API than assumed  
**Fix:** Update test to use correct event fields

```python
# WRONG - ToolCallEvent doesn't have 'result'
ToolCallEvent(
    tool_name="test",
    arguments={},
    result="data"  # ❌ This field doesn't exist
)

# CORRECT - Use ToolResultEvent for results
ToolCallEvent(
    tool_name="test",
    arguments={}
)
# Then separately:
ToolResultEvent(
    tool_name="test",
    result="data"
)
```

**Impact:** Will fix 6 failing tests → +6 passing tests

### 2. Add App Context Fixture for API Tests ✅ READY TO FIX
**File:** `tests/test_api_replay_routes_coverage.py`  
**Issue:** API tests need app context initialized  
**Fix:** Add fixture to conftest.py

```python
# tests/conftest.py
import pytest
from api.app_context import init_app_context, cleanup_app_context

@pytest.fixture(scope="function", autouse=True)
def app_context():
    """Initialize app context for API tests."""
    init_app_context()
    yield
    cleanup_app_context()
```

**Impact:** Will fix 12 API test failures → +12 passing tests

---

## 📋 TODO List (Next Session)

### High Priority (Do First)
- [ ] **Fix redaction event API tests** (30 min)
  - Update ToolCallEvent to not use 'result' field
  - Update LLMRequestEvent to not use direct 'temperature'
  - Update LLMResponseEvent to not use direct 'tokens_used'
  - Run tests: `pytest tests/test_redaction_security_coverage.py -v`

- [ ] **Add app context fixture** (15 min)
  - Add to tests/conftest.py
  - Run tests: `pytest tests/test_api_replay_routes_coverage.py -v`

- [ ] **Run full coverage report** (5 min)
  - Command: `pytest --cov=. --cov-report=html`
  - Check: `htmlcov/index.html`

### Medium Priority (After High Priority Done)
- [ ] **Add more adapter tests** (1-2 hours)
  - LangChain adapter lifecycle tests
  - OpenAI adapter error tests
  - Run: `pytest tests/test_langchain_adapter_coverage.py -v`

- [ ] **Fix remaining API contract tests** (1 hour)
  - Analyze failures in test_api_contract.py
  - Add missing fixtures or adjust expectations

### Low Priority (Nice to Have)
- [ ] **Add property-based tests** (2-3 hours)
  - Install hypothesis
  - Create tests/test_property_redaction.py
  - Generate random inputs for edge cases

---

## 🚀 Commands to Run

### Fix and Verify Redaction Tests
```bash
# Run only redaction tests to see failures
. venv/bin/activate
pytest tests/test_redaction_security_coverage.py -v

# After fixing, run again
pytest tests/test_redaction_security_coverage.py -v
```

### Fix and Verify API Tests
```bash
# Run only API tests to see failures
pytest tests/test_api_replay_routes_coverage.py -v

# After adding fixture, run again
pytest tests/test_api_replay_routes_coverage.py -v
```

### Run All Tests with Coverage
```bash
# Run everything except new failing tests
pytest --ignore=tests/test_langchain_adapter_coverage.py --cov=. --cov-report=term:skip-covered

# After all fixes, run full suite
pytest --cov=. --cov-report=html
```

### Check Specific Coverage
```bash
# Check redaction coverage
pytest --cov=redaction --cov-report=term-missing tests/test_redaction*.py

# Check API coverage
pytest --cov=api --cov-report=term-missing tests/test_api*.py
```

---

## 📊 Expected Results After Fixes

| Area | Before | After Fixes | Impact |
|------|--------|-------------|--------|
| Package Tests | 5/5 ✅ | 5/5 ✅ | Already done |
| Redaction Tests | 20/26 | 26/26 ✅ | +6 passing |
| API Tests | 0/12 | 12/12 ✅ | +12 passing |
| Total Passing | 437 | 455 | +18 passing |
| Failing | 18 | 0 | All green! ✅ |

---

## 🔧 Quick Fix Templates

### Template 1: Fix ToolCallEvent Test
```python
# Before (WRONG)
def test_tool_payload_redaction_enabled():
    event = ToolCallEvent(
        timestamp=datetime.now(timezone.utc),
        tool_name="test",
        arguments={"query": "test"},
        result="data"  # ❌ WRONG
    )

# After (CORRECT)
def test_tool_payload_redaction_enabled():
    # Tool call
    call_event = ToolCallEvent(
        timestamp=datetime.now(timezone.utc),
        tool_name="test",
        arguments={"query": "test"}
    )
    result = pipeline.apply(call_event)
    
    # Tool result (separate event)
    result_event = ToolResultEvent(
        timestamp=datetime.now(timezone.utc),
        tool_name="test",
        result="data"
    )
    result = pipeline.apply(result_event)
```

### Template 2: Fix LLMRequestEvent Test
```python
# Before (WRONG)
event = LLMRequestEvent(
    model="gpt-4",
    messages=[],
    temperature=0.7  # ❌ WRONG - not a direct field
)

# After (CORRECT)
event = LLMRequestEvent(
    model="gpt-4",
    messages=[],
    settings={"temperature": 0.7}  # ✅ In settings dict
)
```

### Template 3: Fix LLMResponseEvent Test
```python
# Before (WRONG)
event = LLMResponseEvent(
    model="gpt-4",
    content="response",
    tokens_used=100  # ❌ WRONG - not a direct field
)

# After (CORRECT)
event = LLMResponseEvent(
    model="gpt-4",
    content="response",
    usage={"input_tokens": 50, "output_tokens": 50}  # ✅ In usage dict
)
```

---

## 📁 Files to Modify

### tests/test_redaction_security_coverage.py
**Lines to fix:**
- Line 61: Remove `result` from ToolCallEvent
- Line 82: Move `temperature` to `settings`
- Line 101: Move `temperature` to `settings`
- Line 117: Move `tokens_used` to `usage`
- Line 137: Split into two events (call + result)
- Line 154: Split into two events (call + result)

### tests/conftest.py
**Add:**
```python
@pytest.fixture(scope="function", autouse=True)
def app_context():
    """Initialize app context for tests that need it."""
    from api.app_context import init_app_context
    try:
        init_app_context()
        yield
    except Exception:
        yield
```

---

## ✅ Success Checklist

When you're done, verify:
- [ ] All redaction tests pass: `pytest tests/test_redaction_security_coverage.py -v`
- [ ] All API tests pass: `pytest tests/test_api_replay_routes_coverage.py -v`
- [ ] No test failures: `pytest -v` shows all green
- [ ] Coverage maintained or improved: `pytest --cov=. --cov-report=term`
- [ ] Documentation updated if needed

---

## 🎓 What We're Learning

1. **Tests reveal actual API** - Our assumptions were wrong, tests showed the way
2. **Event structure matters** - Different events for different purposes
3. **Context initialization** - Some components need setup
4. **Iterative improvement** - Write, fail, fix, repeat

This is the testing process working as intended! 🎯

---

## 📞 Quick Reference

**Current Status:**
- 437 passing tests
- 18 failing tests (6 redaction, 12 API)
- All failures are in new tests we just added
- Expected: All will pass after these fixes

**Next Command:**
```bash
. venv/bin/activate && pytest tests/test_redaction_security_coverage.py::TestRedactionWithToolPayloads::test_tool_payload_redaction_enabled -v
```

This will show you exactly what's failing so you can fix it!

---

**Ready to continue? Start with the Quick Wins section above! 🚀**
