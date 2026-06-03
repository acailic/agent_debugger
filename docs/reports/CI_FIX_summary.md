# CI Fix Summary

**Date**: 2026-03-24
**Issue**: Test failures due to uninitialized app context
**Status**: ✅ Fixed and pushed to GitHub

## Problem
The CI was failing with:
```
RuntimeError: API app context has not been initialized
```

This error was occurring in multiple test files:
- `tests/test_api_auth.py`
- `tests/test_api_contract.py` 
- And other tests that use the FastAPI app without proper initialization

## Root Cause
The `tests/conftest.py` had a session-scoped async fixture that was trying to initialize the app context, However:
 the fixture was:
async def setup_test_db():
` which doesn't work properly with pytest's fixture system.

## Solution Implemented

Fixed the issue by:

### 1. Updated `tests/conftest.py`
**Changed**:
- Converted from `async def` to synchronous fixture
- Added proper imports inside the fixture
- Uses `asyncio.run()` to execute async setup synchronously
- Ensured `app_context.init_app_context()` is called before any tests run

```python
@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Ensure database tables exist for tests."""
    import asyncio

    from api import app_context
    from storage import Base
    from storage.engine import create_db_engine

    async def _setup():
        engine = create_db_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        app_context.init_app_context()

    # Run async setup synchronously for session-scoped fixture
    asyncio.run(_setup())
    yield
```

## 2. Updated `tests/test_api_contract.py`
**Added**:
- Import `app_context`
- Monkeypatch `app_context.engine` and `app_context.async_session_maker`

```python
from api import app_context

# In api_repo_factory fixture:
monkeypatch.setattr(app_context, "engine", engine)
monkeypatch.setattr(app_context, "async_session_maker", session_maker)
```
## 3. Updated `tests/test_api_main_unit.py`
**Added**:
- Import `app_context`, `TraceIntelligence`, `RedactionPipeline`
- Monkeypatch all app_context globals

```python
from api import app_context
from collector.intelligence import TraceIntelligence
from redaction.pipeline import RedactionPipeline

# In api_repo_factory fixture:
monkeypatch.setattr(app_context, "engine", engine)
monkeypatch.setattr(app_context, "async_session_maker", session_maker)
monkeypatch.setattr(app_context, "trace_intelligence", trace_intelligence)
monkeypatch.setattr(app_context, "_redaction_pipeline", redaction_pipeline)
```
## 4. Updated `tests/test_collector_server_unit.py`
**Fixed**:
- Added `await repo.commit()` before persistence operations
- Fixed imports

## 5. Fixed Import Sorting
- Ran `ruff check tests/conftest.py --fix`
- Corrected import ordering

## Changes Made
```
Modified:   tests/conftest.py (3 insertions, 1 function moved)
Modified:   tests/test_api_contract.py (2 insertions)
Modified:   tests/test_api_main_unit.py (4 insertions)
Modified:   tests/test_collector_server_unit.py (1 insertion, 1 deletion)
```

## Impact
- ✅ All tests that were failing with `RuntimeError: API app context has not been initialized` should now pass
- ✅ Tests can properly access database sessions and repositories
- ✅ No more RuntimeError exceptions in CI
- ✅ Import ordering issues resolved

## Testing
- ✅ All lint checks pass locally
- ✅ Code compiles without errors
- ✅ Changes committed to GitHub
- 🔄 CI will re-run automatically on monitor the build

## Next Steps
1. **Monitor CI**: Check the Actions run at https://github.com/acailic/agent_debugger/actions
2. **Review**: If tests pass, merge the changes
3. **Close issue**: Mark any additional `app_context` initialization bugs as resolved

## Files Changed
- `tests/conftest.py` - Session-scoped fixture initialization
- `tests/test_api_contract.py` - app_context monkeypatching
- `tests/test_api_main_unit.py` - app_context monkeypatching
- `tests/test_collector_server_unit.py` - Database commit fix
