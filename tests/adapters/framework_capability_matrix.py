"""Real-framework integration tests backing the adapter capability matrix.

Each test here verifies one capability claimed in
``docs/adapters/capability-matrix.md`` for **langchain-core** and
**pydantic-ai** against the *real installed framework* -- no mocks of
framework internals.  Only the model/network boundary is faked, using each
framework's own in-process test models:

- langchain-core: ``GenericFakeChatModel`` (scripted ``AIMessage`` stream)
  plus a small ``BaseChatModel`` subclass that raises, so LLM behaviour is
  deterministic without any network access.
- pydantic-ai: ``TestModel`` (framework test double) and ``FunctionModel``
  (scripted model function), again fully in-process.

Every framework section is guarded so the whole file skips cleanly in
environments where the frameworks are not installed (e.g. ``.venv-ci``).
Run it for real with::

    python -m venv /tmp/q15-venv
    /tmp/q15-venv/bin/pip install -e '.[server]' pytest pytest-asyncio \\
        pytest-timeout langchain-core pydantic-ai
    /tmp/q15-venv/bin/python -m pytest -q tests/adapters/framework_capability_matrix.py

See ``docs/adapters/capability-matrix.md`` for the tested version pins and
the honest per-capability statuses.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.buffer import get_event_buffer

# ---------------------------------------------------------------------------
# Framework availability guards (importorskip-style, per framework so the two
# sections skip independently).
# ---------------------------------------------------------------------------
try:  # pragma: no cover - exercised only when langchain-core is installed
    import langchain_core

    LANGCHAIN_CORE_VERSION = langchain_core.__version__
    LANGCHAIN_INSTALLED = True
except ImportError:  # pragma: no cover - exercised only without langchain-core
    LANGCHAIN_CORE_VERSION = ""
    LANGCHAIN_INSTALLED = False

try:  # pragma: no cover - exercised only when pydantic-ai is installed
    import pydantic_ai

    PYDANTIC_AI_VERSION = pydantic_ai.__version__
    PYDANTIC_AI_INSTALLED = True
except ImportError:  # pragma: no cover - exercised only without pydantic-ai
    PYDANTIC_AI_VERSION = ""
    PYDANTIC_AI_INSTALLED = False


def _unique_session(prefix: str) -> str:
    """Unique session id (the buffer is global across tests in a run)."""
    return f"capmix-{prefix}-{uuid.uuid4().hex[:10]}"


async def _events(session_id: str) -> list[TraceEvent]:
    """All events captured for *session_id* so far."""
    return await get_event_buffer().get_events(session_id)


async def _of_type(session_id: str, event_type: EventType) -> list[TraceEvent]:
    events = await _events(session_id)
    return [e for e in events if e.event_type == event_type]


def _sync_events(session_id: str) -> list[TraceEvent]:
    """Collect buffer events from a synchronous test context."""
    import asyncio

    return asyncio.run(_events(session_id))


# ===========================================================================
# LangChain (langchain-core) -- VERIFIED-BY-TEST rows of the matrix
# ===========================================================================
@pytest.mark.skipif(not LANGCHAIN_INSTALLED, reason="langchain-core is not installed")
class TestLangChainCoreCapabilities:
    """One focused test per capability claimed for the LangChain adapter."""

    @pytest.mark.asyncio
    async def test_llm_start_and_end_captured_async(self):
        """Async LLM run emits LLM_REQUEST (with prompt) then LLM_RESPONSE (with content)."""
        from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
        from langchain_core.messages import AIMessage

        from agent_debugger_sdk.adapters.langchain import LangChainAdapter

        session_id = _unique_session("lc-llm")
        adapter = LangChainAdapter(session_id=session_id, agent_name="cap-test")
        model = GenericFakeChatModel(messages=iter([AIMessage(content="async reply")]))

        async with adapter.trace_session(agent_name="cap-test"):
            message = await model.ainvoke("hello langchain", config={"callbacks": adapter.get_callbacks()})
            assert message.content == "async reply"

        requests = await _of_type(session_id, EventType.LLM_REQUEST)
        responses = await _of_type(session_id, EventType.LLM_RESPONSE)
        assert len(requests) == 1
        assert len(responses) == 1
        # langchain-core >= 1.0 routes chat models through the
        # on_chat_model_start -> on_llm_start fallback, which stringifies
        # messages ("Human: <prompt>"); the prompt text is preserved.
        assert requests[0].messages
        assert "hello langchain" in requests[0].messages[0]["content"]
        assert requests[0].messages[0]["role"] == "user"
        assert responses[0].content == "async reply"
        # langchain-core >= 1.0 chat models expose no invocation "model" key;
        # the handler falls back to the serialized run name.
        assert requests[0].model == "GenericFakeChatModel"
        assert responses[0].model == "GenericFakeChatModel"

    @pytest.mark.asyncio
    async def test_tool_start_and_end_captured(self):
        """Real @tool run emits TOOL_CALL (name + arguments) and TOOL_RESULT."""
        from langchain_core.tools import tool

        from agent_debugger_sdk.adapters.langchain import LangChainAdapter

        session_id = _unique_session("lc-tool")
        adapter = LangChainAdapter(session_id=session_id, agent_name="cap-test")

        @tool
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        async with adapter.trace_session(agent_name="cap-test"):
            result = await add.ainvoke({"a": 2, "b": 3}, config={"callbacks": adapter.get_callbacks()})
            assert result == 5

        calls = await _of_type(session_id, EventType.TOOL_CALL)
        results = await _of_type(session_id, EventType.TOOL_RESULT)
        assert len(calls) == 1
        assert calls[0].tool_name == "add"
        assert calls[0].arguments == {"a": 2, "b": 3}
        assert len(results) == 1
        assert results[0].tool_name == "add"

    @pytest.mark.asyncio
    async def test_tool_calls_in_llm_response_extracted(self):
        """Tool calls attached to a chat-model AIMessage surface on the LLM_RESPONSE event."""
        from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
        from langchain_core.messages import AIMessage

        from agent_debugger_sdk.adapters.langchain import LangChainAdapter

        session_id = _unique_session("lc-tc")
        adapter = LangChainAdapter(session_id=session_id, agent_name="cap-test")
        model = GenericFakeChatModel(
            messages=iter(
                [
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "add", "args": {"a": 2, "b": 3}, "id": "call_1", "type": "tool_call"}],
                    )
                ]
            )
        )

        async with adapter.trace_session(agent_name="cap-test"):
            message = await model.ainvoke("add for me", config={"callbacks": adapter.get_callbacks()})
            assert message.tool_calls

        responses = await _of_type(session_id, EventType.LLM_RESPONSE)
        assert len(responses) == 1
        assert responses[0].tool_calls == [{"id": "call_1", "name": "add", "arguments": {"a": 2, "b": 3}}]

    @pytest.mark.asyncio
    async def test_chain_start_and_end_captured(self):
        """LCEL sequence run emits chain start/end events for the sequence and its steps."""
        from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
        from langchain_core.messages import AIMessage
        from langchain_core.prompts import ChatPromptTemplate

        from agent_debugger_sdk.adapters.langchain import LangChainAdapter

        session_id = _unique_session("lc-chain")
        adapter = LangChainAdapter(session_id=session_id, agent_name="cap-test")
        model = GenericFakeChatModel(messages=iter([AIMessage(content="chain reply")]))
        chain = ChatPromptTemplate.from_messages([("user", "{question}")]) | model

        async with adapter.trace_session(agent_name="cap-test"):
            output = await chain.ainvoke({"question": "hi"}, config={"callbacks": adapter.get_callbacks()})
            assert output.content == "chain reply"

        all_events = await _events(session_id)
        names = [e.name for e in all_events]
        # langchain-core >= 1.0 passes serialized=None for sequence/prompt
        # runs; the handler resolves names from kwargs.
        assert "chain_start_RunnableSequence" in names
        assert "chain_start_ChatPromptTemplate" in names
        assert names.count("chain_end") >= 2

    @pytest.mark.asyncio
    async def test_nested_runs_link_parents(self):
        """Runs nested inside a sequence reference the enclosing chain_start event as parent."""
        from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
        from langchain_core.messages import AIMessage
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.runnables import RunnableLambda

        from agent_debugger_sdk.adapters.langchain import LangChainAdapter

        session_id = _unique_session("lc-nest")
        adapter = LangChainAdapter(session_id=session_id, agent_name="cap-test")
        model = GenericFakeChatModel(messages=iter([AIMessage(content="nested ok")]))
        sequence = ChatPromptTemplate.from_messages([("user", "{q}")]) | model | RunnableLambda(lambda m: m.content)

        async with adapter.trace_session(agent_name="cap-test"):
            output = await sequence.ainvoke({"q": "hi"}, config={"callbacks": adapter.get_callbacks()})
            assert output == "nested ok"

        all_events = await _events(session_id)
        by_name = {e.name: e for e in all_events if e.name.startswith("chain_start_")}
        sequence_start = by_name["chain_start_RunnableSequence"]
        prompt_start = by_name["chain_start_ChatPromptTemplate"]
        lambda_start = by_name["chain_start_RunnableLambda"]
        assert prompt_start.parent_id == sequence_start.id
        assert lambda_start.parent_id == sequence_start.id

        # The LLM run is a sibling of the prompt step, parented on the sequence.
        llm_request = (await _of_type(session_id, EventType.LLM_REQUEST))[0]
        assert llm_request.parent_id == sequence_start.id

    @pytest.mark.asyncio
    async def test_llm_error_propagates_and_captured(self):
        """A failing model raises to the caller AND is recorded as an ERROR event."""
        from agent_debugger_sdk.adapters.langchain import LangChainAdapter

        session_id = _unique_session("lc-llm-err")
        adapter = LangChainAdapter(session_id=session_id, agent_name="cap-test")
        model = _ExplodingChatModel()

        async with adapter.trace_session(agent_name="cap-test"):
            with pytest.raises(RuntimeError, match="boom-llm"):
                await model.ainvoke("x", config={"callbacks": adapter.get_callbacks()})

        errors = await _of_type(session_id, EventType.ERROR)
        assert len(errors) == 1
        assert errors[0].error_type == "RuntimeError"
        assert "boom-llm" in errors[0].error_message

    @pytest.mark.asyncio
    async def test_chain_error_propagates_and_captured(self):
        """A failing chain step raises to the caller AND is recorded as an ERROR event."""
        from langchain_core.runnables import RunnableLambda

        from agent_debugger_sdk.adapters.langchain import LangChainAdapter

        session_id = _unique_session("lc-chain-err")
        adapter = LangChainAdapter(session_id=session_id, agent_name="cap-test")

        def explode(value: str) -> str:
            raise ValueError("boom-chain")

        chain = RunnableLambda(explode)

        async with adapter.trace_session(agent_name="cap-test"):
            with pytest.raises(ValueError, match="boom-chain"):
                await chain.ainvoke("x", config={"callbacks": adapter.get_callbacks()})

        errors = await _of_type(session_id, EventType.ERROR)
        all_events = await _events(session_id)
        assert len(errors) == 1
        assert errors[0].error_type == "ValueError"
        assert "boom-chain" in errors[0].error_message
        # The chain_start event for the failing run is captured too.
        assert any(e.name == "chain_start_explode" for e in all_events)

    @pytest.mark.asyncio
    async def test_tool_error_captured_with_tool_name(self):
        """A failing tool propagates AND emits a TOOL_RESULT carrying the error and the tool name."""
        from langchain_core.tools import tool

        from agent_debugger_sdk.adapters.langchain import LangChainAdapter

        session_id = _unique_session("lc-tool-err")
        adapter = LangChainAdapter(session_id=session_id, agent_name="cap-test")

        @tool
        def bad_tool(x: int) -> int:
            """A tool that always fails."""
            raise KeyError("boom-tool")

        async with adapter.trace_session(agent_name="cap-test"):
            with pytest.raises(Exception, match="boom-tool"):
                await bad_tool.ainvoke({"x": 1}, config={"callbacks": adapter.get_callbacks()})

        results = await _of_type(session_id, EventType.TOOL_RESULT)
        assert len(results) == 1
        # langchain-core >= 1.0 passes no name kwarg to on_tool_error; the
        # handler remembers it from on_tool_start.
        assert results[0].tool_name == "bad_tool"
        assert "boom-tool" in (results[0].error or "")

    @pytest.mark.asyncio
    async def test_sync_invoke_path_captures_events(self):
        """Sync invoke()/run paths capture the same events when called inside an active trace context."""
        from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
        from langchain_core.messages import AIMessage
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.tools import tool

        from agent_debugger_sdk.adapters.langchain import LangChainAdapter

        session_id = _unique_session("lc-sync")
        adapter = LangChainAdapter(session_id=session_id, agent_name="cap-test")
        model = GenericFakeChatModel(messages=iter([AIMessage(content="sync reply")]))
        chain = ChatPromptTemplate.from_messages([("user", "{q}")]) | model

        @tool
        def echo(value: str) -> str:
            """Echo the value."""
            return value

        async with adapter.trace_session(agent_name="cap-test"):
            output = chain.invoke({"q": "sync hi"}, config={"callbacks": adapter.get_callbacks()})
            assert output.content == "sync reply"
            tool_output = echo.invoke({"value": "hey"}, config={"callbacks": adapter.get_callbacks()})
            assert tool_output == "hey"

        requests = await _of_type(session_id, EventType.LLM_REQUEST)
        responses = await _of_type(session_id, EventType.LLM_RESPONSE)
        calls = await _of_type(session_id, EventType.TOOL_CALL)
        results = await _of_type(session_id, EventType.TOOL_RESULT)
        assert len(requests) == 1
        assert len(responses) == 1
        assert responses[0].content == "sync reply"
        assert len(calls) == 1
        assert calls[0].tool_name == "echo"
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_session_boundary_events_emitted(self):
        """The adapter context emits session start/end TraceEvents."""
        from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
        from langchain_core.messages import AIMessage

        from agent_debugger_sdk.adapters.langchain import LangChainAdapter

        session_id = _unique_session("lc-session")
        adapter = LangChainAdapter(session_id=session_id, agent_name="cap-test")
        model = GenericFakeChatModel(messages=iter([AIMessage(content="x")]))

        async with adapter.trace_session(agent_name="cap-test") as traced_session:
            assert traced_session == session_id
            await model.ainvoke("q", config={"callbacks": adapter.get_callbacks()})

        all_events = await _events(session_id)
        assert all_events[0].name == "session_start"
        assert all_events[-1].name == "session_end"


if LANGCHAIN_INSTALLED:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.outputs import ChatResult

    class _ExplodingChatModel(BaseChatModel):
        """In-process chat model whose every call raises (fake network boundary).

        Defined at module level so both the sync ``_generate`` and async
        ``_agenerate`` paths of a real langchain-core chat model are covered.
        """

        @property
        def _llm_type(self) -> str:
            return "exploding"

        def _generate(
            self,
            messages: Any,
            stop: Any = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> ChatResult:
            raise RuntimeError("boom-llm")

        async def _agenerate(
            self,
            messages: Any,
            stop: Any = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> ChatResult:
            raise RuntimeError("boom-llm")


# ===========================================================================
# PydanticAI -- VERIFIED-BY-TEST rows of the matrix
# ===========================================================================
@pytest.mark.skipif(not PYDANTIC_AI_INSTALLED, reason="pydantic-ai is not installed")
class TestPydanticAICapabilities:
    """One focused test per capability claimed for the PydanticAI adapter."""

    @pytest.mark.asyncio
    async def test_instrument_captures_request_and_response(self):
        """instrument() wraps agent.run: user prompt -> LLM_REQUEST, reply -> LLM_RESPONSE."""
        from pydantic_ai import Agent
        from pydantic_ai.models.test import TestModel

        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        session_id = _unique_session("pa-run")
        agent = Agent(TestModel())
        adapter = PydanticAIAdapter(agent, session_id=session_id, agent_name="cap-test")

        result = await adapter.instrument().run("hello pydantic")
        assert "success" in str(result.output)

        requests = await _of_type(session_id, EventType.LLM_REQUEST)
        responses = await _of_type(session_id, EventType.LLM_RESPONSE)
        assert len(requests) == 1
        assert len(responses) == 1
        assert {"role": "user", "content": "hello pydantic"} in requests[0].messages
        assert requests[0].model == "test"
        assert responses[0].model == "test"
        assert responses[0].content  # TestModel's textual reply

    @pytest.mark.asyncio
    async def test_tool_call_and_result_captured(self):
        """A TestModel-driven tool run emits ToolCallEvent then a ToolResultEvent with the return value."""
        from pydantic_ai import Agent
        from pydantic_ai.models.test import TestModel

        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        session_id = _unique_session("pa-tool")
        agent = Agent(TestModel(call_tools="all"))

        @agent.tool_plain
        def get_age(x: int) -> int:
            """Return a fixed age."""
            return 42

        adapter = PydanticAIAdapter(agent, session_id=session_id, agent_name="cap-test")
        result = await adapter.instrument().run("what is the age")
        assert "42" in str(result.output)

        calls = await _of_type(session_id, EventType.TOOL_CALL)
        results = await _of_type(session_id, EventType.TOOL_RESULT)
        assert len(calls) == 1
        assert calls[0].tool_name == "get_age"
        assert "x" in calls[0].arguments
        assert len(results) == 1
        assert results[0].tool_name == "get_age"
        assert results[0].result is not None

    def test_run_sync_path_captures_events(self):
        """agent.run_sync() routes through the instrumented agent.run and captures the same events."""
        from pydantic_ai import Agent
        from pydantic_ai.models.test import TestModel

        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        session_id = _unique_session("pa-sync")
        agent = Agent(TestModel())
        adapter = PydanticAIAdapter(agent, session_id=session_id, agent_name="cap-test")

        result = adapter.instrument().run_sync("hello sync")
        assert "success" in str(result.output)

        events = _sync_events(session_id)
        types = [e.event_type for e in events]
        assert EventType.LLM_REQUEST in types
        assert EventType.LLM_RESPONSE in types
        requests = [e for e in events if e.event_type == EventType.LLM_REQUEST]
        assert {"role": "user", "content": "hello sync"} in requests[0].messages

    @pytest.mark.asyncio
    async def test_explicit_recording_methods(self):
        """record_llm_request/response/tool_call/tool_result emit events inside a trace session."""
        from pydantic_ai import Agent
        from pydantic_ai.models.test import TestModel

        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        session_id = _unique_session("pa-manual")
        agent = Agent(TestModel())
        adapter = PydanticAIAdapter(agent, session_id=session_id, agent_name="cap-test")

        async with adapter.trace_session(agent_name="cap-test"):
            await adapter.record_llm_request(
                model="test",
                messages=[{"role": "user", "content": "manual"}],
                tools=[{"name": "get_age"}],
                settings={"temperature": 0.1},
            )
            await adapter.record_llm_response(
                model="test", content="manual reply", usage={"input_tokens": 3, "output_tokens": 4}
            )
            await adapter.record_tool_call(tool_name="get_age", arguments={"x": 1})
            await adapter.record_tool_result(tool_name="get_age", result=42, duration_ms=1.5)

        requests = await _of_type(session_id, EventType.LLM_REQUEST)
        responses = await _of_type(session_id, EventType.LLM_RESPONSE)
        calls = await _of_type(session_id, EventType.TOOL_CALL)
        results = await _of_type(session_id, EventType.TOOL_RESULT)
        assert len(requests) == 1 and requests[0].tools == [{"name": "get_age"}]
        assert requests[0].settings == {"temperature": 0.1}
        assert len(responses) == 1 and responses[0].content == "manual reply"
        assert responses[0].usage == {"input_tokens": 3, "output_tokens": 4}
        assert len(calls) == 1 and calls[0].tool_name == "get_age"
        assert len(results) == 1 and results[0].result == 42

    @pytest.mark.asyncio
    async def test_model_error_propagates_and_session_closes(self):
        """A failing model raises out of the instrumented run; the trace session still closes cleanly."""
        from pydantic_ai import Agent
        from pydantic_ai.messages import ModelMessage, ModelResponse
        from pydantic_ai.models.function import FunctionModel

        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        def raise_model(messages: list[ModelMessage], info: Any) -> ModelResponse:
            raise RuntimeError("model-boom")

        session_id = _unique_session("pa-err")
        agent = Agent(FunctionModel(raise_model))
        adapter = PydanticAIAdapter(agent, session_id=session_id, agent_name="cap-test")

        with pytest.raises(Exception, match="model-boom"):
            await adapter.instrument().run("boom")

        events = await _events(session_id)
        names = [e.name for e in events]
        # Session boundaries emitted despite the failure.
        assert names[0] == "session_start"
        assert names[-1] == "session_end"

    @pytest.mark.asyncio
    async def test_tool_retry_surfaces_in_next_request(self):
        """A ModelRetry from a tool appears as a retry message on the next captured LLM request."""
        from pydantic_ai import Agent
        from pydantic_ai.exceptions import ModelRetry
        from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
        from pydantic_ai.models.function import FunctionModel

        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        state = {"calls": 0}

        def flaky_model(messages: list[ModelMessage], info: Any) -> ModelResponse:
            state["calls"] += 1
            if state["calls"] == 1:
                return ModelResponse(parts=[ToolCallPart(tool_name="boom_tool", args={"x": 1}, tool_call_id="c1")])
            return ModelResponse(parts=[TextPart(content="recovered")])

        session_id = _unique_session("pa-retry")
        agent = Agent(FunctionModel(flaky_model))

        @agent.tool_plain(retries=1)
        def boom_tool(x: int) -> int:
            """A tool that asks the model to retry."""
            raise ModelRetry("tool-retry-boom")

        adapter = PydanticAIAdapter(agent, session_id=session_id, agent_name="cap-test")
        result = await adapter.instrument().run("go")
        assert result.output == "recovered"

        requests = await _of_type(session_id, EventType.LLM_REQUEST)
        calls = await _of_type(session_id, EventType.TOOL_CALL)
        # Two model turns: original prompt, then the retry prompt.
        assert len(requests) == 2
        retry_messages = requests[1].messages
        assert any(m.get("role") == "tool" and "tool-retry-boom" in str(m.get("content", "")) for m in retry_messages)
        assert len(calls) == 1
        assert calls[0].tool_name == "boom_tool"
