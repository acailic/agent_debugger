---
title: Framework Integrations
description: Integrate Peaky Peek with PydanticAI, LangChain, OpenAI, and other AI frameworks
---

# Framework Integrations

Peaky Peek provides multiple integration options for popular AI frameworks. Choose the approach that best fits your codebase.

## Integration Overview

| Framework | Adapter | Auto-Patch | Notes |
|-----------|---------|------------|-------|
| **PydanticAI** | ✅ | ✅ | Full integration |
| **LangChain** | ✅ | ✅ | Handler-based |
| **OpenAI SDK** | ✅ | ✅ | Direct instrumentation |
| **Anthropic** | ✅ | ✅ | Direct instrumentation |
| **CrewAI** | ✅ | ✅ | Agent tracing |
| **AutoGen** | 🚧 | ✅ | Experimental |
| **LlamaIndex** | ✅ | ✅ | Tool and LLM calls |

## PydanticAI Integration

### Adapter Method

```python
import asyncio
from pydantic_ai import Agent
from agent_debugger_sdk import init
from agent_debugger_sdk.adapters import PydanticAIAdapter

init()

async def main() -> None:
    agent = Agent("openai:gpt-4o")
    adapter = PydanticAIAdapter(agent, agent_name="support_agent")

    async with adapter.trace_session() as session_id:
        result = await agent.run("Summarize this issue")
        print(session_id, result)

asyncio.run(main())
```

### Auto-Patch Method

```python
import os
os.environ["PEAKY_PEEK_AUTO_PATCH"] = "pydantic_ai"

import agent_debugger_sdk.auto_patch
from pydantic_ai import Agent

agent = Agent("openai:gpt-4o")
result = await agent.run("Hello")
```

## LangChain Integration

### Handler Method (Recommended)

```python
from agent_debugger_sdk import TraceContext, init
from agent_debugger_sdk.adapters import LangChainTracingHandler

init()

context = TraceContext(session_id="demo", agent_name="langchain_agent", framework="langchain")
handler = LangChainTracingHandler(session_id="demo")
handler.set_context(context)

# Use with LangChain callbacks
result = await agent.arun(
    "What is the weather?",
    callbacks=[handler]
)
```

### Auto-Patch Method

```python
import os
os.environ["PEAKY_PEEK_AUTO_PATCH"] = "langchain"

import agent_debugger_sdk.auto_patch
from langchain.agents import initialize_agent, AgentType, Tool

# Your LangChain code — automatically traced
```

!!! note
    The current LangChain path is handler-based. The auto-patching registry exists in the repo, but the actual zero-code patching path is still being refined.

## OpenAI SDK Integration

### Decorator Method

```python
from agent_debugger_sdk import trace

@trace(name="openai_agent", framework="openai")
async def my_agent(prompt: str) -> str:
    import openai
    client = openai.AsyncOpenAI()
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content
```

### Auto-Patch Method

```bash
PEAKY_PEEK_AUTO_PATCH=openai python my_openai_agent.py
```

### Context Manager Method

```python
from agent_debugger_sdk import TraceContext

async with TraceContext(agent_name="openai_agent", framework="openai") as ctx:
    # Record decision before LLM call
    await ctx.record_decision(
        reasoning="Need to answer user question",
        confidence=0.9,
        chosen_action="call_openai",
    )

    # Your OpenAI call here
    response = await openai_call()

    # Record the result
    await ctx.record_llm_response(
        model="gpt-4o",
        content=response.choices[0].message.content,
        usage=response.usage.model_dump(),
    )
```

## Anthropic SDK Integration

### Decorator Method

```python
from agent_debugger_sdk import trace

@trace(name="anthropic_agent", framework="anthropic")
async def my_agent(prompt: str) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic()
    message = await client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text
```

### Auto-Patch Method

```bash
PEAKY_PEEK_AUTO_PATCH=anthropic python my_anthropic_agent.py
```

## CrewAI Integration

### Auto-Patch Method

```python
import os
os.environ["PEAKY_PEEK_AUTO_PATCH"] = "crewai"

import agent_debugger_sdk.auto_patch
from crewai import Agent, Task, Crew

# Your CrewAI code — automatically traced
researcher = Agent(
    role="Researcher",
    goal="Research AI frameworks",
    backstory="You are an AI researcher"
)

task = Task(
    description="Research the latest in AI",
    expected_output="A summary of AI trends",
    agent=researcher
)

crew = Crew(
    agents=[researcher],
    tasks=[task],
    process="sequential"
)

result = crew.kickoff()
```

## AutoGen Integration

!!! warning "Experimental"
    AutoGen integration is currently experimental. Please report any issues.

```python
import os
os.environ["PEAKY_PEEK_AUTO_PATCH"] = "autogen"

import agent_debugger_sdk.auto_patch
from autogen import AssistantAgent, UserProxyAgent

# Your AutoGen code — automatically traced
assistant = AssistantAgent(
    name="assistant",
    llm_config={"model": "gpt-4"}
)

user_proxy = UserProxyAgent(
    name="user_proxy",
    code_execution_config={"work_dir": "coding"}
)

user_proxy.initiate_chat(
    assistant,
    message="Write a hello world function"
)
```

## LlamaIndex Integration

### Auto-Patch Method

```python
import os
os.environ["PEAKY_PEEK_AUTO_PATCH"] = "llamaindex"

import agent_debugger_sdk.auto_patch
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

# Your LlamaIndex code — automatically traced
documents = SimpleDirectoryReader("data").load_data()
index = VectorStoreIndex.from_documents(documents)
query_engine = index.as_query_engine()
response = query_engine.query("What is the document about?")
```

## Custom Agents

If you're building a custom agent, use the core SDK directly:

### Using TraceContext

```python
from agent_debugger_sdk import TraceContext, init

init()

async def my_custom_agent(prompt: str) -> str:
    async with TraceContext(agent_name="custom_agent", framework="custom") as ctx:
        # Record decisions
        await ctx.record_decision(
            reasoning=f"Processing: {prompt}",
            confidence=0.8,
            chosen_action="analyze",
        )

        # Record tool calls
        await ctx.record_tool_call("analyzer", {"text": prompt})
        result = analyze(prompt)

        # Record results
        await ctx.record_tool_result(
            "analyzer",
            result=result,
            duration_ms=150
        )

        return result
```

### Using Decorators

```python
from agent_debugger_sdk import trace_agent, trace_tool

@trace_tool(name="search")
async def search_tool(query: str) -> dict:
    return {"results": [...]}

@trace_agent(name="research_agent")
async def research_agent(topic: str) -> str:
    results = await search_tool(topic)
    return summarize(results)
```

## Choosing an Integration Method

### Use Adapters When
- The framework has built-in instrumentation hooks
- You want framework-specific event capture
- You're using supported frameworks (PydanticAI, LangChain)

### Use Decorators When
- Your code has clear agent/tool boundaries
- You want minimal code changes
- You want automatic event capture

### Use TraceContext When
- You need fine-grained control over event recording
- You're building a custom agent framework
- You want to capture custom decision points

### Use Auto-Patch When
- You want zero-code instrumentation
- You're prototyping or exploring
- You don't want to modify existing code

## Next Steps

- [Getting Started](getting-started.md) — 5-minute quickstart
- [Installation](installation.md) — Install Peaky Peek
- [Configuration](configuration.md) — Advanced configuration options
- [API Reference](api-reference.md) — SDK and API documentation
