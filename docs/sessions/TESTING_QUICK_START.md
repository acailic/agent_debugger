# Testing Quick Start Guide

**Get to 95% Coverage in 4 Weeks**

---

## 🎯 Current Status (2026-03-24)

```
Coverage: 90%
Tests: 436 passing, 0 failing (core suite)
Files at 100%: 41
```

---

## ⚡ Quick Wins (Do These First)

### 1. Fix Package Test ✅ DONE
- Fixed version test to work in dev mode
- Tests now pass in all environments

### 2. Add Security Tests (Priority: CRITICAL)

Create `tests/security/test_redaction_critical.py`:

```python
"""Critical security tests for redaction."""
import pytest
from datetime import datetime, timezone
from redaction.pipeline import RedactionPipeline
from agent_debugger_sdk.core.events import TraceEvent, EventType

class TestRedactionSecurity:
    def test_password_redaction(self):
        """Ensure passwords are always redacted."""
        pipeline = RedactionPipeline(redact_pii=True)
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data={"password": "secret123"}
        )
        result = pipeline.process_event(event)
        assert result.data["password"] != "secret123"
    
    def test_api_key_redaction(self):
        """Ensure API keys are redacted."""
        pipeline = RedactionPipeline(redact_pii=True)
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data={"api_key": "sk-1234567890"}
        )
        result = pipeline.process_event(event)
        assert "sk-1234567890" not in str(result.data)
```

### 3. Add API Error Tests (Priority: HIGH)

Create `tests/api/test_replay_errors.py`:

```python
"""Error handling tests for replay routes."""
import pytest
from fastapi.testclient import TestClient
from api.main import create_app

@pytest.fixture
def client():
    return TestClient(create_app())

class TestReplayErrors:
    def test_replay_invalid_session_id(self, client):
        """Test replay with invalid session ID."""
        response = client.get("/api/sessions/invalid/replay")
        assert response.status_code in [400, 404]
    
    def test_replay_nonexistent_session(self, client):
        """Test replay with session that doesn't exist."""
        import uuid
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/sessions/{fake_id}/replay")
        assert response.status_code in [400, 404]
```

---

## 📊 Coverage Targets by Week

| Week | Target | Focus | Files to Improve |
|------|--------|-------|------------------|
| 1 | 92% | Security | `redaction/pipeline.py`, `api/replay_routes.py` |
| 2 | 93% | Adapters | `langchain_adapter.py`, `openai_adapter.py` |
| 3 | 94% | Edge Cases | All adapters to 85%+ |
| 4 | 95%+ | Polish | Remove all files below 80% |

---

## 🔧 Commands

### Run Tests with Coverage
```bash
. venv/bin/activate
pytest --cov=. --cov-report=term-missing -q
```

### Run Specific Test File
```bash
pytest tests/test_package.py -v
```

### Run Security Tests Only
```bash
pytest tests/security/ -v
```

### Generate HTML Coverage Report
```bash
pytest --cov=. --cov-report=html
open htmlcov/index.html
```

---

## 📁 Test Organization

```
tests/
├── security/           # NEW: Security-focused tests
│   ├── test_redaction_critical.py
│   └── test_auth_security.py
├── api/               # NEW: API-specific tests
│   ├── test_replay_errors.py
│   └── test_session_errors.py
├── integration/       # Integration tests
├── unit/              # Unit tests
└── property/          # Property-based tests
```

---

## ⚠️ High-Priority Gaps

### 1. Redaction (83% → 95%)
**Missing Lines:** 66, 94-96, 126, 130, 137, 147-157, 169, 192-203, 209, 219  
**Risk:** PII leakage  
**Action:** Add security tests for all edge cases

### 2. Replay Routes (69% → 90%)
**Missing Lines:** 80, 99-121  
**Risk:** Poor error handling  
**Action:** Test all error scenarios

### 3. LangChain Adapter (71% → 85%)
**Missing Lines:** 90-91, 109-111, 134-135, 164, 173-174, etc.  
**Risk:** Integration failures  
**Action:** Test callback edge cases

---

## ✅ Testing Checklist

For each module you're testing:

- [ ] Normal case works
- [ ] Empty input handled
- [ ] None/null handled
- [ ] Invalid input rejected
- [ ] Errors handled gracefully
- [ ] Security implications considered
- [ ] Performance acceptable
- [ ] Documentation updated

---

## 🎓 Common Patterns

### Pattern 1: Test Event Creation
```python
from datetime import datetime, timezone
from agent_debugger_sdk.core.events import TraceEvent, EventType

def create_test_event(data):
    return TraceEvent(
        event_type=EventType.TOOL_CALL,
        timestamp=datetime.now(timezone.utc),
        data=data
    )
```

### Pattern 2: Test Client Setup
```python
from fastapi.testclient import TestClient
from api.main import create_app

@pytest.fixture
def client():
    return TestClient(create_app())
```

### Pattern 3: Mock External Dependencies
```python
from unittest.mock import patch, Mock

@patch('module.external_call')
def test_with_mock(mock_call):
    mock_call.return_value = Mock(value="test")
    # Test code here
```

---

## 🚨 Security Test Requirements

Every security-sensitive module needs:

1. **Injection Tests**
   - SQL injection attempts
   - Script injection
   - Template injection

2. **PII Tests**
   - Email addresses
   - Credit cards
   - SSNs
   - API keys

3. **Edge Cases**
   - Empty strings
   - Very long strings
   - Unicode characters
   - Special characters

4. **Malformed Input**
   - Invalid JSON
   - Circular references
   - Deeply nested structures

---

## 📈 Progress Tracking

### Week 1 Checklist
- [x] Fix package version test
- [ ] Add 20 security tests
- [ ] Add 15 API error tests
- [ ] Reach 92% coverage

### Week 2 Checklist
- [ ] Add 25 adapter tests
- [ ] Add 10 integration tests
- [ ] Reach 93% coverage

### Week 3 Checklist
- [ ] Add property-based tests
- [ ] Add performance tests
- [ ] Reach 94% coverage

### Week 4 Checklist
- [ ] Review all tests
- [ ] Add missing edge cases
- [ ] Reach 95%+ coverage

---

## 💬 Getting Help

1. **Check Documentation**
   - `TESTING_IMPROVEMENT_PLAN.md`
   - `TESTING_LEARNINGS_AND_RECOMMENDATIONS.md`
   - `TESTING_SUMMARY.md`

2. **Review Examples**
   - `tests/test_package.py` - Good test structure
   - `tests/test_api_main_unit.py` - Comprehensive testing
   - `tests/test_redaction.py` - Security testing

3. **Common Issues**
   - Import errors: Check Python path
   - Fixture issues: Use pytest fixtures
   - Async issues: Use pytest-asyncio

---

## 🎯 Success Criteria

You're done when:
- [ ] Coverage ≥ 95%
- [ ] No files below 80%
- [ ] All security paths tested
- [ ] All error paths tested
- [ ] CI/CD integrated
- [ ] Documentation complete

---

**Start Here:** Pick one module from "High-Priority Gaps" and add tests until it reaches 95% coverage.

**Questions?** Check the detailed docs or existing test files for examples.
