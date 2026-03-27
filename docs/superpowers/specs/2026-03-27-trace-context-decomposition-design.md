# TraceContext Decomposition — Complete the Package Migration

**Date**: 2026-03-27
**Status**: Approved

## Problem

The `core/context.py` monolith (523 lines) was partially decomposed into a `core/context/` package in commit `dccc4e3`. However:

- The old `context.py` still exists and shadows the package
- All 40+ import sites still point at the old monolith
- `CheckpointManager` and `TransportService` are only referenced from the old monolith and are dead code
- The new `trace_context.py` has equivalent behavior with simpler transport wiring

## Design

### Delete

- `core/context.py` — old monolith, fully replaced by `core/context/` package
- `core/checkpoint_manager.py` — dead code (only imported by old `context.py`)
- `core/transport_service.py` — dead code (only imported by old `context.py`)

### Keep as-is

- `core/context/__init__.py` — package root with re-exports
- `core/context/trace_context.py` — new TraceContext (inline checkpoint logic, direct HttpTransport)
- `core/context/session_manager.py` — extracted session lifecycle management
- `core/context/pipeline.py` — event pipeline configuration
- `core/context/vars.py` — ContextVar declarations and accessors

### Import updates (no API surface change)

All imports of the form `from agent_debugger_sdk.core.context import X` continue to work because the package `__init__.py` re-exports everything. The old module shadowing is removed by deleting `context.py`.

Files that need verification (imports should work as-is after deletion):
- `core/__init__.py`, `core/decorators.py`, `core/decorators/agent.py`, `core/decorators/llm.py`, `core/decorators/tool.py`
- `adapters/langchain.py`, `adapters/pydantic_ai.py`
- `agent_debugger_sdk/__init__.py`
- `api/main.py`
- ~15 test files, 2 script files

### Behavioral differences (new vs old)

- **Old**: Uses `TransportService.configure_for_cloud_mode()` which checks `config.mode == "cloud" and config.api_key`
- **New**: Checks `config.api_key` directly and instantiates `HttpTransport` inline
- **Result**: The new version is more lenient (works when api_key is set regardless of mode). This is the intended behavior.

## Verification

- `ruff check .`
- `python3 -m pytest -q` (full suite)
- `cd frontend && npm run build` (ensure no frontend breakage)
