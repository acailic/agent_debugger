# Test-First Foundation

**Date:** 2026-03-27
**Status:** Approved
**Scope:** SDK core testing + API contracts

## Problem

The SDK core (`agent_debugger_sdk/core/`) has minimal unit test coverage. This creates risk:
- Refactoring is unsafe without test coverage
- Adapters depend on core behavior that isn't verified
- API contract changes can silently break the SDK

## Goal

Build reliable test coverage for SDK core and critical API contracts before any major refactoring.

**Target:** 70%+ line coverage on `agent_debugger_sdk/core/` plus verified SDK↔API contracts.

## Scope

### In Scope
- `agent_debugger_sdk/core/context/` — TraceContext, session lifecycle
- `agent_debugger_sdk/core/events/` — Event types, serialization
- `agent_debugger_sdk/core/recorders.py` — Record decision, tool, LLM
- `agent_debugger_sdk/core/emitter.py` — Event emission, batching
- SDK → API contract tests — verify session/event/replay payloads match schemas

### Out of Scope
- Adapters (LangChain, PydanticAI) — keep existing integration tests
- Frontend component tests
- Auto-patch extensions
- Pricing module

## Design

### Test Structure

```
tests/
├── sdk/
│   ├── core/
│   │   ├── test_context.py        # TraceContext, session lifecycle
│   │   ├── test_events.py         # Event types, serialization
│   │   ├── test_recorders.py      # Record decision, tool, LLM
│   │   └── test_emitter.py        # Event emission, batching
│   └── contract/
│       └── test_api_contract.py   # SDK payloads ↔ API schemas
└── (existing tests remain unchanged)
```

### Test Categories

1. **Unit tests** — Pure SDK logic, no I/O, fast execution
2. **Contract tests** — SDK event payloads match `api/schemas.py` exactly

### Test Style

Plain pytest with no additional abstractions. Use `pytest-asyncio` only where async testing is required.

```python
# Example test structure
def test_trace_context_records_decision():
    ctx = TraceContext(agent_name="test", framework="custom")
    # ... assertions
```

## Verification

Run after implementation:

```bash
python3 -m pytest tests/sdk/ -v --cov=agent_debugger_sdk/core --cov-report=term-missing
```

Success criteria:
- All tests pass
- Coverage report shows 70%+ on core modules
- Contract tests verify all event types

## Risks

| Risk | Mitigation |
|------|------------|
| Async code complexity | Use pytest-asyncio sparingly, prefer sync wrappers for testing |
| Schema drift | Contract tests fail CI if SDK and API diverge |
| Test maintenance | Keep tests simple and focused on behavior, not implementation |

## Next Steps

1. Create test file structure
2. Implement core unit tests (context, events, recorders, emitter)
3. Implement contract tests
4. Add coverage reporting to CI
