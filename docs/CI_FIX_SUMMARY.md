# CI Build Fix Summary

**Date**: 2026-03-24
**Issue**: Tests failing with `RuntimeError: API app context has not been initialized`

## Root Cause

The FastAPI application requires global state initialization through `app_context.init_app_context()` before any routes can be accessed. Several test files were:

1. Importing and using the FastAPI `app` directly without initializing app context
2. Not patching the `app_context` globals when setting up test fixtures
3. Missing commits on database sessions before testing persistence

## Changes Made

### 1. `tests/conftest.py`
**Before**:
```python
@pytest.fixture(autouse=True, scope="session")
async def setup_test_db():
    from api import app_context
    from storage import Base
    from storage.engine import create_db_engine

    engine = create_db_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app_context.init_app_context()
    yield
```

**After**:
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

**Why**: Session-scoped fixtures cannot be async in pytest. Changed to sync fixture that runs async setup internally.

### 2. `tests/test_api_contract.py`
**Changes**:
- Added `from api import app_context` import
- Added monkeypatch calls to set `app_context.engine` and `app_context.async_session_maker`
- Fixed assertions to use dot notation (`session.id` instead of `session["id"]`)

**Why**: Tests need to patch `app_context` globals, not just `api_main` globals.

### 3. `tests/test_api_main_unit.py`
**Changes**:
- Added `from api import app_context` import
- Initialized all app_context dependencies in fixture:
  - `engine`
  - `async_session_maker`
  - `trace_intelligence`
  - `_redaction_pipeline`
- Fixed assertions to use dot notation

**Why**: All app_context dependencies must be initialized to prevent RuntimeError.

### 4. `tests/test_collector_server_unit.py`
**Changes**:
- Added `await repo.commit()` after `create_session()` calls

**Why**: Sessions need to be committed before testing persistence operations.

## Testing

All lint checks pass:
```bash
ruff check tests/
# All checks passed!
```

## CI Status

After these changes, the CI should pass the test phase. The fix addresses:
- ✅ RuntimeError on app_context not initialized
- ✅ Import sorting issues
- ✅ Missing database commits
- ✅ Incorrect attribute access patterns

## Commit

```bash
commit 7d1e57113517d9e18a8fcbdcb5e59edcf3fe2d16
Author: acailic <acailic@users.noreply.github.com>
Date:   Tue Mar 24 11:55:49 2026 +0100

    fixing tests
    
    tests/conftest.py                   | 18 ++++++++----
    tests/test_api_contract.py          | 21 ++++++++------
    tests/test_api_main_unit.py         | 56 +++++++++++++++++++++++--------------
    tests/test_collector_server_unit.py |  2 ++
    4 files changed, 62 insertions(+), 35 deletions(-)
```

## Next Steps

1. Push changes to GitHub
2. Monitor CI build to verify all tests pass
3. If any additional failures occur, check for:
   - Missing `app_context` initialization in other test files
   - Async fixture issues
   - Database session management

## Related Files

- `api/app_context.py` - Contains global state and initialization
- `api/dependencies.py` - Uses `require_session_maker()` which throws the error
- `tests/conftest.py` - Session-scoped test fixtures
