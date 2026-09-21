# Adapter capability matrix

Status: **DRAFT — first supported version set (roadmap W07, queue item Q15), published 2026-09-21.**

One row per registered adapter and capability. Statuses mean exactly this and
nothing more:

| Status | Meaning |
| --- | --- |
| **VERIFIED-BY-TEST** | A test in `tests/adapters/framework_capability_matrix.py` exercises this capability against the **real installed framework** (no mocks of framework internals; only the model/network boundary is faked with the framework's own in-process test models) and passes. The referenced test is listed in the row. |
| **MOCKED-ONLY** | The adapter has unit tests with hand-built mocks/fakes of the framework. No test runs against the real package. The capability may work, but this repo has no evidence. |
| **NOT SUPPORTED** | The adapter does not implement this capability (by code inspection). Not claimed, not tested. |

## Tested framework versions (first supported version set)

| Framework | Tested version | Date | Notes |
| --- | --- | --- | --- |
| langchain-core | **1.6.3** | 2026-09-21 | Verified via `GenericFakeChatModel`, LCEL `RunnableSequence`/`RunnableLambda`/`ChatPromptTemplate`, real `@tool`s. |
| pydantic-ai | **2.46.0** (pydantic-ai-slim 2.46.0) | 2026-09-21 | Verified via `TestModel` and `FunctionModel` (no network). |
| openai / anthropic / crewai / autogen / llamaindex | — | — | Not installed in the verification environment; rows below are MOCKED-ONLY or NOT SUPPORTED by code inspection. |

## Matrix

Legend for VERIFIED-BY-TEST references: `capmx` = `tests/adapters/framework_capability_matrix.py`.

### `agent_debugger_sdk/adapters/langchain/` — LangChainTracingHandler / LangChainAdapter (registered as `langchain`)

| Capability | Status | Evidence / notes |
| --- | --- | --- |
| Sessions | VERIFIED-BY-TEST | `capmx::test_session_boundary_events_emitted` — `session_start` / `session_end` events bracket the trace. |
| LLM calls | VERIFIED-BY-TEST | `capmx::test_llm_start_and_end_captured_async`, `::test_sync_invoke_path_captures_events` — async and sync invoke both emit `LLMRequestEvent` + `LLMResponseEvent`. Caveats: langchain-core ≥ 1.0 routes chat models through the `on_chat_model_start → on_llm_start` fallback, so prompts arrive stringified (`"Human: <prompt>"`); the model label is best-effort (invocation params first, else the serialized run name, e.g. `GenericFakeChatModel`). |
| Tools | VERIFIED-BY-TEST | `capmx::test_tool_start_and_end_captured`, `::test_tool_calls_in_llm_response_extracted` — `ToolCallEvent` (name + arguments from `kwargs["inputs"]`) and `ToolResultEvent`; tool calls attached to an `AIMessage` surface on the LLM response event. |
| Chains / graphs | VERIFIED-BY-TEST (LCEL runnables) | `capmx::test_chain_start_and_end_captured`, `::test_nested_runs_link_parents` — start/end `AGENT_START`/`AGENT_END` events for `RunnableSequence`, `ChatPromptTemplate`, `RunnableLambda`, with correct parent linkage. **LangGraph is NOT SUPPORTED** (no adapter exists). |
| Decisions | NOT SUPPORTED | No adapter API records `DecisionEvent`. Users can call `TraceContext.record_decision` manually inside the trace session. |
| Errors | VERIFIED-BY-TEST | `::test_llm_error_propagates_and_captured`, `::test_chain_error_propagates_and_captured`, `::test_tool_error_captured_with_tool_name` — exceptions propagate to the caller AND `ErrorEvent` / errored `ToolResultEvent` are captured. |
| Streaming | NOT SUPPORTED | The handler implements no `on_llm_new_token` callback; streamed token runs are not captured. |
| Cancellation | NOT SUPPORTED | No cancellation-specific handling; a cancelled run simply never fires the end callbacks. |
| Checkpoint participation | NOT SUPPORTED | The tracing handler creates no checkpoints. (Restore-side: `agent_debugger_sdk/checkpoints/hooks.py` has a separate LangChain restore hook, not exercised by these tests.) |

### `agent_debugger_sdk/adapters/pydantic_ai/` — PydanticAIAdapter (registered as `pydanticai`)

| Capability | Status | Evidence / notes |
| --- | --- | --- |
| Sessions | VERIFIED-BY-TEST | `capmx::test_model_error_propagates_and_session_closes` (and every other test) — `session_start` / `session_end` bracket the run, including on failure. |
| LLM calls | VERIFIED-BY-TEST | `::test_instrument_captures_request_and_response`, `::test_run_sync_path_captures_events` — `instrument()` wraps `agent.run`; `run` and `run_sync` paths both emit `LLMRequestEvent` + `LLMResponseEvent` with model name resolved from the agent (`"test"`, `"function:…"`). Caveat: events are derived from `result.all_messages()` **after the run completes**, so mid-run visibility is not provided. |
| Tools | VERIFIED-BY-TEST | `::test_tool_call_and_result_captured`, `::test_tool_retry_surfaces_in_next_request` — `ToolCallEvent` and `ToolResultEvent` with return values; a `ModelRetry` from a tool surfaces as a role-`tool` retry message on the next captured request. |
| Chains / graphs | NOT SUPPORTED | Only the single-agent run envelope is traced; no multi-agent graph or handoff capture. |
| Decisions | NOT SUPPORTED | No adapter API records `DecisionEvent`. |
| Errors | VERIFIED-BY-TEST (partial shape) | `::test_model_error_propagates_and_session_closes` — model exceptions propagate out of the instrumented run and the session still closes cleanly. Tool failures that request a retry are captured as retry messages, **not** as `ErrorEvent`/errored `ToolResultEvent`; unretried tool failures propagate unrecorded. |
| Explicit recording | VERIFIED-BY-TEST | `::test_explicit_recording_methods` — `record_llm_request` / `record_llm_response` / `record_tool_call` / `record_tool_result` emit events inside `trace_session()`. |
| Streaming | NOT SUPPORTED | `run_stream` / `iter` / `agent.iter` are not wrapped by `instrument()`. |
| Cancellation | NOT SUPPORTED | No cancellation-specific handling. |
| Checkpoint participation | NOT SUPPORTED | No pydantic-ai checkpoint hook exists. |

### Auto-patch provider adapters (`agent_debugger_sdk/auto_patch/adapters/`)

Zero-instrumentation monkey-patches of client libraries. **All evidence for
these is MOCKED-ONLY**: their tests (`tests/auto_patch/test_openai_adapter.py`,
`tests/auto_patch/test_anthropic_adapter.py`) stub the client libraries; no
real-framework run is claimed or tested.

| Capability | `openai` | `anthropic` |
| --- | --- | --- |
| Sessions | MOCKED-ONLY (auto session via background transport) | MOCKED-ONLY |
| LLM calls | MOCKED-ONLY (non-streaming `chat.completions.create`, sync + async clients) | MOCKED-ONLY (non-streaming `messages.create`, sync + async) |
| Tools | MOCKED-ONLY (`ToolCallEvent` from response choices) | MOCKED-ONLY |
| Chains / graphs | NOT SUPPORTED | NOT SUPPORTED |
| Decisions | NOT SUPPORTED | NOT SUPPORTED |
| Errors | NOT SUPPORTED (exceptions propagate; no `ErrorEvent` is emitted by the patch) | NOT SUPPORTED |
| Streaming | NOT SUPPORTED (documented pass-through: `stream=True` is not intercepted) | NOT SUPPORTED (same) |
| Cancellation | NOT SUPPORTED | NOT SUPPORTED |
| Checkpoint participation | NOT SUPPORTED | NOT SUPPORTED |

### Auto-patch orchestration adapters (run-envelope only)

`crewai`, `autogen` (v0.2 `initiate_chat` / v0.4 `AssistantAgent.run`),
`llamaindex` (`BaseQueryEngine.query`/`aquery`). These emit **only**
`AGENT_START` / `AGENT_END` for the top-level run — deliberately treated as
partial adapters (roadmap W07 wording). All evidence is MOCKED-ONLY
(`tests/auto_patch/test_crewai_adapter.py`, `test_autogen_adapter.py`,
`test_llamaindex_adapter.py`).

| Capability | `crewai` | `autogen` | `llamaindex` |
| --- | --- | --- | --- |
| Sessions | MOCKED-ONLY | MOCKED-ONLY | MOCKED-ONLY |
| LLM calls | NOT SUPPORTED | NOT SUPPORTED | NOT SUPPORTED |
| Tools | NOT SUPPORTED | NOT SUPPORTED | NOT SUPPORTED |
| Chains / graphs | NOT SUPPORTED (crew envelope only) | NOT SUPPORTED (chat/agent envelope only) | NOT SUPPORTED (query envelope only) |
| Decisions | NOT SUPPORTED | NOT SUPPORTED | NOT SUPPORTED |
| Errors | NOT SUPPORTED | NOT SUPPORTED | NOT SUPPORTED |
| Streaming | NOT SUPPORTED | NOT SUPPORTED | NOT SUPPORTED |
| Cancellation | NOT SUPPORTED | NOT SUPPORTED | NOT SUPPORTED |
| Checkpoint participation | NOT SUPPORTED | NOT SUPPORTED | NOT SUPPORTED |

## Adapter fixes made for the tested versions (API drift)

The LangChain handler (`agent_debugger_sdk/adapters/langchain/handler.py`)
was written against langchain-core ≤ 0.3 call signatures; the following
minimal, backwards-compatible fixes were required for langchain-core 1.6.3:

1. `serialized` is `None` for most runnables in ≥ 1.0 (`RunnableSequence`,
   `RunnableLambda`) — `on_chain_start` / `on_tool_start` now guard against
   `None` and resolve names from `kwargs["name"]`.
2. Structured tool input moved to `kwargs["inputs"]` — `on_tool_start`
   prefers it over the stringified `input_str`.
3. `on_tool_error` receives no `name` kwarg in ≥ 1.0 — the name remembered
   by `on_tool_start` is reused.
4. Chat models no longer carry `model` in `invocation_params` — the model
   label falls back to the serialized run name / kwargs name, and
   `on_llm_end` reuses the label resolved at `on_llm_start`.

The PydanticAI adapter needed **no code changes** for pydantic-ai 2.46.0;
its `instrument()` run-wrapping, `run_sync` routing, and message processing
(`all_messages`, `ToolCallPart`, `ToolReturnPart`, `RetryPromptPart`) all
work as written. One behavioural note: plain exceptions in tools no longer
auto-retry in pydantic-ai ≥ 1.0 — tools must raise `ModelRetry` for the
retry-capture path.

## How to run the real-framework suite

```bash
# Scratch venv OUTSIDE the repo (do not install into .venv-ci):
python3 -m venv /tmp/q15-venv
/tmp/q15-venv/bin/pip install -e '.[server]' pytest pytest-asyncio pytest-timeout \
    'langchain-core==1.6.3' 'pydantic-ai==2.46.0'

/tmp/q15-venv/bin/python -m pytest -q -o addopts='' \
    tests/adapters/framework_capability_matrix.py
# -> 16 passed (10 langchain-core + 6 pydantic-ai) as of 2026-09-21
```

In environments without the frameworks (e.g. `.venv-ci`) the same command
skips every test:

```bash
.venv-ci/bin/python -m pytest -q -o addopts='' tests/adapters/framework_capability_matrix.py
# -> 16 skipped
```

The existing mocked adapter suites stay green in both environments:

```bash
.venv-ci/bin/python -m pytest -q agent_debugger_sdk/adapters/tests/ tests/auto_patch/
/tmp/q15-venv/bin/python -m pytest -q -o addopts='' agent_debugger_sdk/adapters/tests/ tests/auto_patch/
```
