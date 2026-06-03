# Real-World Agent Failure Patterns for Testing

> Research compiled from production usage of major agent frameworks: LangChain, Pydantic AI, OpenAI SDK, CrewAI, and AutoGen.

## Purpose

This document catalogs real-world failure patterns observed in production AI agents. Use these patterns to:
1. Design more realistic test scenarios beyond synthetic benchmarks
2. Ensure the SDK captures the telemetry needed to debug these failures
3. Validate that the debugger UI can surface and explain these patterns

---

## Summary: Failure Pattern Categories

| Category | Description | Current Benchmark Coverage |
|----------|-------------|---------------------------|
| Output Parsing | LLM output doesn't match expected format | ❌ Not covered |
| Context Management | Context window overflow, state drift | ❌ Not covered |
| Error Recovery | Rate limits, timeouts, malformed responses | ❌ Not covered |
| Retry Cascades | Multiple retry layers interacting | ❌ Not covered |
| Multi-Agent Coordination | Delegation failures, auth, conversation limits | Partial (multi_agent_dialogue) |
| Long-Running Sessions | Memory leaks, state accumulation over time | ❌ Not covered |
| Tool Failures | External API failures, cascading errors | Partial (failure_cluster) |
| Loop Detection | Infinite loops, circular reasoning | Partial (looping_behavior) |

---

## Framework-Specific Failure Patterns

### 1. LangChain

**Source**: [langchain-ai/langchain](https://github.com/langchain-ai/langchain)

#### Output Parsing Failures
- **`OutputParserException`**: LLM output doesn't conform to expected format
- LLM may deviate from prompt instructions for structuring responses
- Exception includes `observation` and `llm_output` for self-correction attempts

#### Context Overflow
- **`ContextOverflowError`**: Input (prompt + history + tool outputs) exceeds context window
- Common in agents with long conversation histories or large tool outputs

#### Agent Stopping Conditions
- Agents stop at `max_iterations` or `max_execution_time` limits
- Need to handle graceful termination with meaningful error messages
- Test case: `max_iterations=0` returns "Agent stopped due to iteration limit or time limit."

#### Bad Actions and Tool Usage
- Invalid actions when agent output is not a valid action
- Misuse of tools with wrong parameters
- Result: predefined failure messages

#### Testing Strategies Used by LangChain
- **FakeListLLM**: Deterministic LLM responses for testing
- **FakeRetriever**: Fixed document retrieval
- **Snapshot testing** with `syrupy` for schema stability
- **`langchain-tests`**: Standardized test base classes for integrations
- **Callbacks/Tracing**: `LangChainTracer` sends traces to LangSmith

---

### 2. Pydantic AI

**Source**: [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai)

#### Common Issues
- **Jupyter event loop errors**: `RuntimeError: This event loop is already running`
- **API key configuration**: `UserError: API key must be provided`

#### Error Handling Philosophy
- **Explicit errors**: Framework raises errors for unsupported features rather than silent degradation
- **Graceful degradation**: `ModelResponse` with empty `parts=[]` but populated metadata for recoverable failures
- **`UnexpectedModelBehavior`**: Raised when models exceed retry limits or return API errors

#### Retry Mechanisms (Multiple Layers)
1. **Tool retries**: Tools configured with `retries` parameter
2. **Output validation retries**: Agent prompted to retry on validation failure
3. **HTTP request retries**: Configurable retry policies for HTTPX clients

#### Debugging & Observability
- **Logfire integration**: OpenTelemetry-based observability
- **`capture_run_messages()`**: Access messages exchanged during run for diagnosis
- **Detailed traces**: Visibility into messages, tool calls, token usage, latency, errors
- **HTTPX instrumentation**: Monitor raw HTTP requests/responses

---

### 3. OpenAI SDK

**Source**: [openai/openai-python](https://github.com/openai/openai-python)

#### Error Hierarchy
All errors inherit from `openai.APIError`:
- `openai.APIConnectionError`: Network issues or timeouts
- `openai.APIStatusError`: Non-success HTTP status codes
  - `BadRequestError` (400)
  - `AuthenticationError` (401)
  - `RateLimitError` (429)
  - `InternalServerError` (5xx)

#### Automatic Retries
- **Default**: 2 retries with exponential backoff
- Retries: network issues, 408, 409, 429, 5xx errors
- Respects `Retry-After` header
- Configurable via `max_retries` option

#### Request IDs
- Every response includes `_request_id` from `x-request-id` header
- Critical for debugging with OpenAI support
- Available in both success responses and `APIStatusError` exceptions

#### Debugging Features
- **Logging**: Set `OPENAI_LOG=info` or `debug`
- **Raw response**: `.with_raw_response` for headers, status codes, raw body
- **Streaming**: `.with_streaming_response` for large payloads

#### Edge Cases
- **Pydantic model refusal**: Model refuses to generate response fitting schema (safety policies)
- **Max tokens reached**: `LengthFinishReasonError` when output exceeds `max_tokens`
- **Distinguishing `None`**: Use `response.model_fields_set` to differentiate null from missing

---

### 4. CrewAI

**Source**: [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI)

#### LLM Selection Pitfalls
- **"One model fits all" trap**: Same LLM for all agents regardless of task complexity
- **LLM hierarchy conflicts**: Crew-level, manager-level, agent-level settings conflicting
- **Mismatched function calling**: Models not optimized for tool usage struggling with parameters
- **Context/memory limitations**: Long-running conversations exceeding limits

#### Task Definition Issues
- Vague tasks lacking necessary context
- Unclear success criteria
- Combined unrelated objectives

#### Agent-to-Agent (A2A) Communication Failures
- **Connection errors**: Remote agents unreachable (network/endpoints)
- **Authentication errors**: Invalid or expired tokens
- **Timeout errors**: Tasks exceed configured `timeout`
- **Max turns exceeded**: `max_turns` limit reached before completion
- **Transport negotiation failures**: Client/server can't agree on protocol (JSONRPC, gRPC, HTTP+JSON)

#### What Breaks in Production
- Unreliable external services (APIs down, slow, unexpected data)
- LLM non-determinism (inconsistent behavior)
- Context window limitations
- Rate limiting on frequent API calls
- Misconfigured authentication
- **Infinite loops** from recursive delegation without `max_turns`
- Lack of observability (hard to identify root cause)

---

### 5. AutoGen

**Source**: [microsoft/autogen](https://github.com/microsoft/autogen)

#### General Risks
- Privacy and data protection concerns
- Accountability and transparency challenges
- Trust and reliance on AI systems
- Security risks from code execution or function calls

#### Observability (OpenTelemetry)
- **Runtime instrumentation**: `SingleThreadedAgentRuntime`, `GrpcWorkerAgentRuntime`
- **GenAI semantic conventions**: For agent operations and tool execution
- **Configuration**: `trace_provider` or `AUTOGEN_DISABLE_RUNTIME_TRACING=true`

#### Logging Modes
1. **Trace logging**: Human-readable for developers (`autogen_core.trace`)
2. **Structured logging**: Machine-consumable events (`autogen_core.event`)

---

## Proposed Test Scenarios

Based on the patterns above, here are test scenarios that would exercise real-world failure modes:

### Scenario: Output Parsing Failure & Recovery
```
1. LLM returns malformed JSON
2. SDK captures OutputParserException
3. Agent attempts self-correction
4. Trace shows parsing error + retry
```

### Scenario: Rate Limit Cascade
```
1. Multiple tool calls hit rate limits
2. SDK captures 429 errors with Retry-After headers
3. Exponential backoff kicks in
4. Trace shows retry timing and eventual success/failure
```

### Scenario: Context Overflow
```
1. Long-running agent accumulates context
2. Context window exceeded mid-conversation
3. SDK captures ContextOverflowError
4. Trace shows context size growth over time
```

### Scenario: Multi-Agent Delegation Timeout
```
1. Agent A delegates to Agent B
2. Agent B times out (slow external service)
3. A2A timeout error propagated
4. Trace shows delegation chain + timeout point
```

### Scenario: Retry Cascade (Tool → Validation → HTTP)
```
1. Tool fails → tool retry
2. Tool succeeds but validation fails → validation retry
3. Validation passes but HTTP fails → HTTP retry
4. SDK captures full retry chain with reasons
```

### Scenario: Long-Running State Drift
```
1. Agent runs for 100+ turns
2. State accumulates, memory grows
3. Early decisions conflict with new context
4. SDK captures state evolution and decision conflicts
```

### Scenario: Infinite Loop Detection
```
1. Agent enters circular reasoning pattern
2. Same tool called with same parameters repeatedly
3. Loop detected after N iterations
4. SDK captures loop signature + intervention point
```

---

## Current Benchmark Gaps

| Current Benchmark | Real Patterns It Covers | Gaps |
|-------------------|------------------------|------|
| `prompt_injection` | Safety checks, refusals, policy violations | No output parsing failures |
| `evidence_grounding` | Tool calls, decisions with evidence | No rate limits, no retries |
| `multi_agent_dialogue` | Multiple speakers, turns | No delegation failures, no timeouts |
| `prompt_policy_shift` | Policy changes | No context overflow |
| `safety_escalation` | Escalating safety events | No retry cascades |
| `looping_behavior` | Parent chain loops | No infinite loop detection/intervention |
| `failure_cluster` | Repeated tool failures | No error recovery, no rate limit handling |
| `replay_determinism` | Checkpoints, refusals | No long-running session simulation |

---

## Testing Strategy Recommendations

### 1. Record/Replay for Real Framework Integration
- Run actual LangChain/CrewAI/Pydantic AI agents
- Record HTTP interactions (VCR-style)
- Replay in CI without API keys
- Refresh recordings periodically

### 2. Deterministic "Fake" Servers
- Small local model or mock LLM server
- Predictable responses for edge cases
- No API costs, fully reproducible

### 3. Chaos Engineering
- Inject failures: timeouts, malformed responses, rate limits
- Test recovery paths
- Verify observability captures failure signatures

### 4. Long-Running Session Simulation
- Generate sessions with 100+ events
- Simulate state drift over time
- Test memory and context management

### 5. Multi-Agent Orchestration Tests
- Real A2A communication (even if mocked endpoints)
- Timeout and auth failure scenarios
- Delegation chain debugging

---

## References

- [LangChain Testing Guide](https://python.langchain.com/docs/contributing/tests)
- [Pydantic AI Documentation](https://ai.pydantic.dev/)
- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [CrewAI Documentation](https://docs.crewai.com/)
- [AutoGen Documentation](https://microsoft.github.io/autogen/)
