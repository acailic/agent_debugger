# Competitive Analysis: Peaky Peek

**Date:** 2026-03-26
**Scope:** Direct competitors in AI agent debugging/observability — Arize Phoenix, Langfuse, LangSmith, AgentOps, LiteLLM
**Focus:** Framework support (PydanticAI + LangChain), feature depth, strategic positioning

---

## Executive Summary

The AI agent observability market has ~15 tools, but only **two** are genuine direct competitors to Peaky Peek: **Arize Phoenix** (open-source, local-first, PydanticAI + LangChain support, 9K stars) and **Langfuse** (open-source MIT, self-hosted, 23K stars). Both have deeper feature breadth (evaluation, prompt management, analytics) but lack Peaky Peek's core differentiators: decision provenance, checkpoint-based replay, and true debugging depth.

The remaining three — **LangSmith** (SaaS-only, LangChain-native), **AgentOps** (SaaS platform, no PydanticAI), and **LiteLLM** (gateway, not a debugger) — overlap at the tracing layer but serve fundamentally different use cases.

**Peaky Peek's strategic position:** Win on debugging depth and PydanticAI support. Do not try to match feature breadth of Phoenix/Langfuse.

### Threat Assessment

| Competitor | Threat Level | Why |
|-----------|-------------|-----|
| **Arize Phoenix** | HIGH | Open-source, local-first, PydanticAI + LangChain, backed by Arize AI |
| **Langfuse** | HIGH | Open-source MIT, largest feature set, 23K stars, active community |
| **LangSmith** | MEDIUM | Market leader for LangChain but SaaS-only, no PydanticAI |
| **AgentOps** | MEDIUM | Agent-specific but SaaS-only, no PydanticAI |
| **LiteLLM** | LOW | Primarily complementary (gateway), not a debugger |

---

## 1. Arize Phoenix

### Positioning

Open-source LLM observability and evaluation platform. True local-first design — runs entirely on your machine via `pip install`. Built on OpenInference semantic conventions (the OTel standard for LLM spans). Backed by Arize AI (VC-funded).

| Metric | Value |
|--------|-------|
| GitHub | [Arize-ai/phoenix](https://github.com/Arize-ai/phoenix) |
| Stars | ~9,037 |
| License | Apache 2.0 |
| Releases | Multiple per week (v13.18.2, March 24 2026) |
| Backing | Arize AI |
| Community | Slack, GitHub Discussions |

### PydanticAI Support

**Official, first-class integration** via `openinference-instrumentation-pydantic-ai`.

- **Mechanism:** OpenTelemetry instrumentor with `auto_instrument=True` in `phoenix.otel.register()`
- **Agent flag:** Requires `instrument=True` on each `Agent()` constructor — not fully automatic
- **Setup:**
  ```python
  # pip install arize-phoenix openinference-instrumentation-pydantic-ai
  from phoenix.otel import register
  register(project_name="my-app", auto_instrument=True)
  agent = Agent(model, output_type=MyModel, instrument=True)
  ```
- **Captures:** Agent runs, structured outputs, tool calls, LLM calls, performance metrics, errors, multi-agent workflows

### LangChain Support

**Official integration** via `openinference-instrumentation-langchain`.

- **Mechanism:** `LangChainInstrumentor` — intercepts LangChain's callback system via OTel
- **LangGraph:** Yes — captures node execution, conditional edges, `Send` API, orchestration
- **Setup:**
  ```python
  # pip install arize-phoenix openinference-instrumentation-langchain
  from phoenix.otel import register
  from openinference.instrumentation.langchain import LangChainInstrumentor
  tracer_provider = register(project_name="my-app", auto_instrument=True)
  LangChainInstrumentor(tracer_provider=tracer_provider).instrument(skip_dep_check=True)
  ```
- **Captures:** Chain/agent spans, LLM calls, tool calls, retriever calls, prompt templates, streaming, errors

### Where Phoenix Beats Peaky Peek

| Area | Detail |
|------|--------|
| Evaluation | Built-in LLM-as-judge with configurable eval chains |
| Prompt playground | Interactive prompt testing and iteration |
| Dataset management | Versioned datasets for regression testing |
| Framework breadth | 25+ instrumentors across Python, JS, Java |
| OpenInference standard | Vendor-neutral, any OTel backend works |
| Analytics dashboards | Rich built-in dashboards for trace analysis |
| Community | 9K stars, 100+ contributors, backed by VC-funded company |

### Where Peaky Peek Beats Phoenix

| Area | Detail |
|------|--------|
| Debugging depth | Phoenix is observability-only — no step-through, no replay, no state inspection |
| Decision provenance | No concept of WHY an agent made a decision |
| Session management | Phoenix treats traces as independent observations, no session grouping |
| Checkpoint replay | No checkpoint system, no time-travel debugging |
| Setup simplicity | Phoenix requires OTel dependency chain (`opentelemetry-sdk`, `opentelemetry-api`, `opentelemetry-exporter-otlp`) |
| Integration model | Phoenix goes through OTel instrumentors; Peaky Peek uses direct Python instrumentation (lighter) |
| Auto-instrumentation | Phoenix requires `instrument=True` per agent; Peaky Peek's auto-patching is more seamless |

### Strategic Implications

Phoenix is the closest competitor in positioning (open-source, local-first) but serves a different primary use case: **evaluation and monitoring** vs. **debugging and replay**. They are complementary more than directly competitive — a team could use Phoenix for evals and Peaky Peek for debugging.

**Action items:**
- Consider adopting OpenInference span conventions for interoperability — users could send Peaky Peek traces to Phoenix for evals
- Phoenix's lack of replay/debugging is our core differentiator — double down here
- Phoenix's 25+ instrumentors highlight Peaky Peek's current framework coverage gap (7 auto-patch adapters vs. 25+)

---

## 2. Langfuse

### Positioning

Open-source LLM engineering platform with the most comprehensive feature set in the market. Tracing, prompt management, evaluation, analytics, datasets, experiments — all in one platform. Y Combinator W23. Self-hosted via Docker Compose.

| Metric | Value |
|--------|-------|
| GitHub | [langfuse/langfuse](https://github.com/langfuse/langfuse) |
| Stars | ~23,800 |
| License | MIT (core); enterprise features in `ee/` folders excluded |
| Releases | Every 2-3 days (v3.162.0, March 24 2026) |
| Backing | Y Combinator W23 |
| Community | Discord, GitHub Discussions, 120+ downstream projects |

### PydanticAI Support

**Official, documented integration** via PydanticAI's built-in OTel instrumentation.

- **Mechanism:** `Agent.instrument_all()` for global OTel instrumentation + `instrument=True` per agent
- **Setup:**
  ```python
  # pip install langfuse pydantic-ai -U
  from langfuse import get_client
  langfuse = get_client()  # uses LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST env vars
  from pydantic_ai.agent import Agent
  Agent.instrument_all()
  roulette_agent = Agent('openai:gpt-4o', deps_type=int, result_type=bool, instrument=True)
  ```
- **Captures:** Agent runs, LLM calls, tool calls, agent inputs/outputs, dependencies (`deps` values)
- **Extras:** Custom span attributes (`user_id`, `session_id`, `tags`, `metadata`), per-span scoring, managed prompts

### LangChain Support

**First-class integration** via callback handler. One of Langfuse's primary integrations.

- **Mechanism:** `langfuse.callback.CallbackHandler` plugs into LangChain's standard callback system
- **LangGraph:** Yes — explicit support, captures `langgraph_step`, `langgraph_node`, `langgraph_path`, `langgraph_checkpoint_ns`
- **Setup:**
  ```python
  # pip install langfuse
  from langfuse.callback import CallbackHandler
  handler = CallbackHandler(secret_key="sk-lf-...", public_key="pk-lf-...", host="https://cloud.langfuse.com")
  chain.invoke({"input": "hello"}, config={"callbacks": [handler]})
  ```
- **Captures:** Full nested trace tree, LLM calls (model, params, tokens, latency), chain I/O, tool calls, retriever calls, streaming, conversation history
- **Supported interfaces:** LCEL, `invoke()`, `run()`, `call()`, `predict()`, async, `batch()`, streaming, LangServe

### Where Langfuse Beats Peaky Peek

| Area | Detail |
|------|--------|
| Feature breadth | Tracing + prompt management + evaluation + datasets + experiments + analytics |
| Prompt management | Centralized version-controlled prompts with caching and A/B testing |
| Evaluation | LLM-as-judge, human annotation, custom pipelines, annotation queues |
| Analytics | Custom dashboards, daily metrics API, production analytics |
| Community | 23K stars, 120+ downstream adopters (langflow, open-webui, ragflow, etc.) |
| Compliance | SOC 2 Type II, ISO 27001, GDPR, HIPAA |
| Dataset experiments | Run agents against benchmark datasets with scoring |

### Where Peaky Peek Beats Langfuse

| Area | Detail |
|------|--------|
| Local-first simplicity | Langfuse needs 6 Docker containers (PostgreSQL, ClickHouse, Redis, MinIO, web, worker) — Peaky Peek is `pip install` + go |
| Self-hosting footprint | Langfuse requires 8GB+ RAM recommended; Peaky Peek runs with SQLite |
| Debugging depth | Langfuse is a tracing platform — no replay, no step-through, no state inspection |
| Decision provenance | No concept of WHY decisions were made |
| Checkpoint replay | No checkpoint system |
| Privacy by default | Langfuse sends telemetry to PostHog by default; Peaky Peek keeps everything local |
| OTel dependency | Langfuse relies on PydanticAI's `instrument_all()` OTel path; Peaky Peek uses direct instrumentation |

### Strategic Implications

Langfuse is the feature king but its self-hosting complexity is a real weakness. Teams that want "just debug my agent locally" will bounce off the 6-container setup. This is Peaky Peek's primary wedge.

**Action items:**
- Lead with "pip install and go" simplicity in all PydanticAI/LangChain onboarding — contrast against Langfuse's Docker Compose
- Langfuse's prompt management and evaluation are table stakes that users will eventually want — consider integration or partnership story
- Langfuse's MIT license and community momentum make it the default "open-source observability" choice — Peaky Peek should position as the debugging layer that works alongside it, not against it

---

## 3. LangSmith

### Positioning

End-to-end tracing, evaluation, and debugging platform built by the LangChain team. The market leader for LangChain/LangGraph observability. SaaS-first with self-hosted options for enterprise.

| Metric | Value |
|--------|-------|
| GitHub | [langchain-ai/langsmith-sdk](https://github.com/langchain-ai/langsmith-sdk) |
| Stars | ~815 (SDK repo; leverages LangChain's 90K+ ecosystem) |
| License | MIT (SDK) |
| Backing | LangChain, Inc. (VC-funded) |
| Compliance | HIPAA, SOC 2 Type II, GDPR |

### PydanticAI Support

**No dedicated integration.** Only generic `@traceable` decorator for manual instrumentation.

- No PydanticAI-specific module in `langsmith/integrations/`
- `@traceable` captures function inputs/outputs, timing, and nesting — no framework-aware data
- No capture of PydanticAI's dependency injection, tool registration, or structured output metadata
- **Verdict:** Shallow and manual. General-purpose observability, not PydanticAI-aware debugging.

### LangChain Support

**Native, first-class.** This is LangSmith's home turf — built by the same team.

- **Mechanism:** Built-in `LangChainTracer` or environment variables (`LANGSMITH_TRACING=true`)
- **LangGraph:** Full native support with conditional branching and state transition visibility
- **Setup:** Zero code changes — just set env vars for LangChain users
- **Captures:** All LLM calls, chain executions, tool calls, retriever steps, agent actions, parent-child relationships, errors

### Key Features

| Feature | Details |
|---------|---------|
| Evaluation | 4 evaluator types, `evaluate()` orchestration, pytest integration with `@test` decorator |
| Datasets | Versioned collections (kv, llm, chat types), upload from CSV/DataFrame |
| Prompt management | Versioning, commits, LangChain Hub integration |
| Insights | AI-generated reports over agent histories (Plus+ tier) |
| Testing | pytest integration, `expect` module, API call caching |
| Deployment | Fleet (no-code deployment), Studio (visual builder) |

### Where LangSmith Beats Peaky Peek

| Area | Detail |
|------|--------|
| LangChain depth | Built by the LangChain team — deepest possible integration |
| Evaluation framework | Mature with 4 evaluator types and pytest integration |
| Feature breadth | Evaluation + prompts + datasets + deployment + testing + insights |
| LangChain ecosystem reach | 90K+ stars on parent repo, default choice for LangChain users |
| Compliance certifications | HIPAA, SOC 2, GDPR |

### Where Peaky Peek Beats Langsmith

| Area | Detail |
|------|--------|
| Local-first | LangSmith is SaaS-first; self-hosting is enterprise only |
| PydanticAI support | Peaky Peek has a native adapter; LangSmith has nothing |
| Debugging depth | LangSmith traces "what happened" — no decision provenance, no checkpoint replay |
| Privacy | LangSmith sends data to cloud; Peaky Peek keeps everything local |
| Open-source | LangSmith's platform is proprietary; Peaky Peek is fully open |
| Safety observability | No safety/refusal-specific views in LangSmith |

### Strategic Implications

LangSmith is the Goliath for LangChain users but irrelevant for PydanticAI. Its SaaS-only default is a structural weakness for teams with data privacy requirements.

**Action items:**
- For PydanticAI users, LangSmith is not a competitor — focus messaging on "the debugger LangSmith can't be"
- For LangChain users, position as "the local-first alternative when you can't send traces to the cloud"
- Do not try to match LangSmith's feature breadth — win on debugging depth and privacy

---

## 4. AgentOps

### Positioning

Agent-specific observability platform designed for autonomous AI agents. Tracks agent sessions, tool calls, errors, and multi-step reasoning. SaaS platform with enterprise self-hosting.

| Metric | Value |
|--------|-------|
| GitHub | [AgentOps-AI/agentops](https://github.com/AgentOps-AI/agentops) |
| Stars | ~5,401 |
| License | Open-source SDK + proprietary platform |
| Backing | AgentOps, Inc. (VC-funded) |
| Compliance | SOC 2, HIPAA, NIST AI RMF (Enterprise) |

### PydanticAI Support

**None.** No adapter, callback handler, or documentation for PydanticAI.

- AgentOps supports: OpenAI Agents SDK, CrewAI, AG2/AutoGen, Camel AI, LangChain, LlamaIndex, SwarmZero, Agno, Haystack, Smolagents
- Manual `@operation` decorator possible but provides only basic span/timing data
- **Verdict:** Complete gap.

### LangChain Support

**Strong native integration** via `LangchainCallbackHandler`.

- **Mechanism:** Single callback handler, auto-initializes client
- **LangGraph:** Yes — auto-instrumentation confirmed
- **Setup:**
  ```python
  from agentops.langchain import LangchainCallbackHandler
  handler = LangchainCallbackHandler()
  chain.invoke({"input": "hello"}, config={"callbacks": [handler]})
  ```
- **Captures:** LLM calls, agent actions, tool usage, session metrics, errors

### Pricing

| Plan | Price | Spans/Month | Key Limits |
|------|-------|-------------|------------|
| Basic | $0 | 5,000 | 1 project, 3-day retention, 30 waterfall spans |
| Pro | $40/mo | 100,000 | Unlimited projects, 10-year retention, all features |
| Enterprise | Custom | Custom | SLA, SSO, self-hosting, compliance |

### Where AgentOps Beats Peaky Peek

| Area | Detail |
|------|--------|
| Framework breadth | 10+ agent frameworks vs. Peaky Peek's 7 auto-patch adapters |
| Session replay UI | Waterfall visualization for agent execution graphs |
| Cost tracking | Highlighted feature with per-call and per-session aggregation |
| Transparent pricing | Clear free tier limits, published pricing |

### Where Peaky Peek Beats AgentOps

| Area | Detail |
|------|--------|
| PydanticAI support | Peaky Peek has a native adapter; AgentOps has nothing |
| Local-first | AgentOps is SaaS; self-hosting is enterprise-only |
| Debugging depth | AgentOps traces "what happened" — no decision provenance, no checkpoint replay |
| Open-source | AgentOps platform is proprietary; Peaky Peek is fully open |
| No retention limits | AgentOps free tier has 3-day retention; Peaky Peek keeps all data locally |
| Safety observability | No safety-specific views in AgentOps |

### Strategic Implications

AgentOps is the weakest direct competitor — narrow feature set, SaaS-only, no PydanticAI. Its broader framework coverage (CrewAI, AutoGen, etc.) is a reminder that Peaky Peek should expand adapter support.

**Action items:**
- Not a priority competitor. Monitor for PydanticAI support (if they add it, reassess)
- AgentOps' broad framework list highlights where Peaky Peek should expand: CrewAI, AutoGen, LlamaIndex already have auto-patch adapters — market these more prominently

---

## 5. LiteLLM

### Positioning

Unified LLM API proxy/gateway for 100+ providers. Tracing and observability are secondary features built on top of the gateway architecture. Primarily complementary infrastructure, not a debugger.

| Metric | Value |
|--------|-------|
| GitHub | [BerriAI/litellm](https://github.com/BerriAI/litellm) |
| Stars | ~40,891 |
| Forks | ~6,742 |
| License | Custom (NOASSERTION on GitHub) |

### PydanticAI Support

**Not a real integration.** PydanticAI agents can be registered as A2A (Agent-to-Agent) protocol endpoints, but this is gateway routing, not instrumentation.

- PydanticAI agents are treated as black-box endpoints
- No visibility into internal tool calls, retry logic, structured output validation, or decision flow
- "Fake streaming" support (PydanticAI doesn't natively stream, LiteLLM polls)
- **Verdict:** Gateway-level visibility only. No agent-level debugging.

### LangChain Support

**Gateway integration** via `ChatLiteLLM` provider + callback-based logging.

- Replaces direct provider calls with LiteLLM's normalized interface
- Callback system forwards traces to third-party observability platforms (Langfuse, LangSmith, Datadog, etc.)
- Captures: LLM call metadata, cost, tokens, latency, user/team attribution
- **Does not** provide its own deep chain tracing — relies on external tools
- **Verdict:** Operational logging layer, not a debugging tool.

### Where LiteLLM Beats Peaky Peek

| Area | Detail |
|------|--------|
| LLM provider coverage | 100+ providers with unified API |
| Infrastructure features | Load balancing, rate limiting, API key management, budgets |
| Community | 40K stars, massive ecosystem |
| Cost tracking | Per-call, per-session, per-customer, per-agent |
| Multi-tenancy | Teams, organizations, SSO |
| Prometheus metrics | Built-in `/metrics` endpoint |

### Where Peaky Peek Beats LiteLLM

| Area | Detail |
|------|--------|
| Agent-level tracing | LiteLLM sees only LLM calls through the proxy — no agent internals |
| Session replay | Not supported |
| Checkpoint debugging | Not supported |
| Decision provenance | Not tracked |
| PydanticAI depth | LiteLLM treats PydanticAI as a black box |
| Local-first architecture | LiteLLM requires PostgreSQL; Peaky Peek uses SQLite |
| Purpose | LiteLLM is a gateway with logging; Peaky Peek is a debugger |

### Strategic Implications

LiteLLM is **primarily complementary**, not competitive. It operates at the LLM routing layer; Peaky Peek operates at the agent framework layer. They can coexist — LiteLLM handles routing/cost and Peaky Peek handles debugging.

**Action items:**
- Do not position against LiteLLM — position alongside it
- Consider adding an integration that captures LiteLLM callback data to enrich Peaky Peek sessions
- If users ask about LiteLLM comparison, clarify: "LiteLLM is a gateway. Peaky Peek is a debugger. Use both."

---

## 6. Summary Comparison Matrix

| Capability | Peaky Peek | Phoenix | Langfuse | LangSmith | AgentOps | LiteLLM |
|-----------|-----------|---------|----------|-----------|----------|---------|
| **License** | Open-source | Apache 2.0 | MIT | Proprietary | OSS SDK + proprietary | Custom |
| **Local-first** | Yes (core identity) | Yes | No (6 containers) | No (SaaS) | No (SaaS) | Partial |
| **PydanticAI** | Native adapter | Official OTel | Official OTel | Manual `@traceable` | None | Black-box gateway |
| **LangChain** | Native adapter | Official OTel | Callback handler | Native (built-in) | Callback handler | Provider + callbacks |
| **LangGraph** | Via adapter | Yes | Yes | Full native | Yes | Delegates to others |
| **Session replay** | Core feature | No | No | Trace replay | Waterfall | No |
| **Checkpoint debugging** | Core feature | No | No | No | No | No |
| **Decision provenance** | Core feature | No | No | No | No | No |
| **Evaluation** | No | Built-in LLM-as-judge | LLM-as-judge + human | Mature (4 types) | Basic | No |
| **Prompt management** | No | Playground | Versioned, A/B | Versioned, Hub | No | No |
| **Cost tracking** | Via pricing.py | No | Yes | Yes | Yes (highlighted) | Yes (core feature) |
| **Dataset experiments** | No | Versioned datasets | Benchmark datasets | Versioned datasets | No | No |
| **Auto-instrumentation** | Yes (auto-patch) | Yes (OTel) | Yes (OTel) | Yes (env vars) | Yes (callback) | N/A (gateway) |
| **Setup complexity** | `pip install` | `pip install` + OTel | Docker Compose (6 services) | API key | API key | `pip install` + config |

### GitHub Stars Comparison

| Project | Stars | Trend |
|---------|-------|-------|
| LiteLLM | ~40,900 | Massive community |
| Langfuse | ~23,800 | Strong growth |
| Phoenix | ~9,000 | Steady growth |
| AgentOps | ~5,400 | Moderate |
| LangSmith SDK | ~815 | Leverages LangChain ecosystem |
| **Peaky Peek** | Early stage | Launching |

---

## 7. Framework-Specific Battle Cards

### PydanticAI Ecosystem

**Competitive landscape is wide open.** Only Phoenix and Langfuse have official PydanticAI integrations, and both go through OpenTelemetry — requiring the `instrument=True` flag on each agent and the OTel dependency chain.

| Tool | Integration Depth | Setup Complexity | What You Get |
|------|-------------------|-----------------|--------------|
| **Peaky Peek** | Framework-aware adapter + auto-patch | Low (`pip install`, env vars) | Decisions, tool calls, structured outputs, replay, checkpoints |
| **Phoenix** | OTel instrumentor | Medium (OTel deps + `instrument=True`) | Traces, evaluation, prompt playground |
| **Langfuse** | OTel via `Agent.instrument_all()` | Medium (OTel deps + `instrument=True`) | Traces, scoring, prompt management, datasets |
| **LangSmith** | Manual `@traceable` | High (manual wrapping) | Basic function-level tracing |
| **AgentOps** | None | N/A | N/A |
| **LiteLLM** | Black-box A2A gateway | Low (gateway config) | Request/response logging only |

**Peaky Peek's PydanticAI win:** We're the only tool that captures agent-level debugging data (decisions, retries, structured output validation) without requiring OTel, with auto-patching available.

### LangChain Ecosystem

**More competitive.** LangSmith is the default for LangChain users. Phoenix and Langfuse both have strong integrations. Peaky Peek competes on debugging depth and privacy.

| Tool | Integration Depth | Setup Complexity | What You Get |
|------|-------------------|-----------------|--------------|
| **LangSmith** | Native (built by LangChain team) | Very low (env vars) | Full tracing, evaluation, prompts, datasets, deployment |
| **Phoenix** | OTel instrumentor | Medium | Traces, evaluation, prompt playground |
| **Langfuse** | Callback handler | Low | Traces, scoring, prompt management, datasets, analytics |
| **AgentOps** | Callback handler | Low | Traces, session replay waterfall, cost tracking |
| **Peaky Peek** | Native adapter + auto-patch | Low (`pip install`, env vars) | Decisions, tool calls, replay, checkpoints, safety events |
| **LiteLLM** | Provider + callbacks | Medium (gateway config) | Cost, latency, delegates deep tracing to others |

**Peaky Peek's LangChain win:** We're the only tool focused on "why did my agent do that" rather than "what did my agent do." Local-first and privacy are differentiators against LangSmith/Langfuse.

---

## 8. Priority Action Items

### Defend (core differentiators — no competitor matches)

1. **Decision provenance** — double down. No competitor tracks why agents make decisions. This is the hero feature from ADR-010.
2. **Checkpoint-based replay** — double down. No competitor offers time-travel debugging. This is the second hero feature.
3. **PydanticAI as first-class citizen** — only Peaky Peek, Phoenix, and Langfuse support it. Our adapter is the most debugging-focused.
4. **Local-first simplicity** — contrast against Langfuse's 6-container setup and LangSmith's SaaS requirement in all messaging.

### Build (features users will expect based on competitor comparison)

5. **Evaluation integration** — Phoenix, Langfuse, and LangSmith all offer LLM-as-judge evaluation. Consider adding evaluation hooks or integrating with Phoenix/Langfuse for eval workflows.
6. **Cost tracking** — LiteLLM, AgentOps, and Langfuse all provide per-call cost analytics. Peaky Peek has `pricing.py` but should make this more visible in the UI.
7. **Framework adapter expansion** — Phoenix has 25+ instrumentors, AgentOps has 10+ frameworks. Prioritize: CrewAI, AutoGen, LlamaIndex (already have auto-patch — need to promote).

### Monitor

8. **Phoenix's trajectory** — closest competitor in positioning. If they add replay/debugging, reassess threat level.
9. **Langfuse's self-hosting simplification** — if they reduce from 6 containers, the local-first argument weakens.
10. **PydanticAI ecosystem growth** — as PydanticAI grows, more tools will add support. First-mover advantage has a window.

---

*Research compiled on 2026-03-26. Sources: GitHub API, DeepWiki, official documentation, web search. LangSmith pricing could not be confirmed (SPA pricing page).*
