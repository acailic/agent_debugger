# Peaky Peek — Submission Materials

Repository: https://github.com/acailic/agent_debugger
PyPI SDK: https://pypi.org/project/peaky-peek/
PyPI Server: https://pypi.org/project/peaky-peek-server/
Demo course: https://acailic.github.io/agent_debugger/peaky-peek-course.html

---

## 1. Product Hunt

### Tagline
Local-first debugger for AI agents — see why your agent did that.

### Description (short)
Peaky Peek is an open-source, local-first debugger for AI agents. Capture decisions, replay from checkpoints, visualize reasoning trees, and detect drift — all on your machine. No data sent anywhere.

Works with LangChain, CrewAI, Pydantic AI, and any custom agent. One pip install, one decorator, full trace.

### Topics / Tags
Developer Tools, Open Source, Artificial Intelligence, Python, Debugging

### First Comment (Maker Comment)

Hey everyone! I built Peaky Peek because I got tired of not being able to answer "why did my agent do that?"

Existing tools like LangSmith are great for LLM tracing, but they're SaaS-first — your prompts and reasoning chains leave your machine. OpenTelemetry is blind to agent reasoning. Sentry catches errors but can't tell you *why* an agent chose a specific action.

**What Peaky Peek does differently:**
- **Local-first** — all data stays on your machine, zero telemetry
- **Causal tracing** — captures the full decision chain, not just LLM calls
- **Checkpoint replay** — restore any point in the agent's execution and replay from there
- **Drift detection** — detect when a restored session diverges from the original
- **Reasoning visualization** — interactive tree view of agent decisions
- **Zero-config mode** — set one env var, no code changes needed

**Install in 10 seconds:**
```bash
pip install peaky-peek-server && peaky-peek --open
```

```python
from agent_debugger_sdk import trace

@trace
async def my_agent(prompt: str) -> str:
    return await llm_call(prompt)
```

Works with LangChain, CrewAI, Pydantic AI, and any custom Python agent. MIT licensed, actively developed.

Would love to hear what you think!

### Screenshots to Upload
- README GIFs from `docs/assets/` (trace visualization, replay, analytics)
- Screenshot of the UI at `http://localhost:8000`

---

## 2. Awesome Lists

### Submission Template (adapt per list)

**Title:** Add Peaky Peek — local-first AI agent debugger

**Body:**
Peaky Peek is an open-source, local-first debugger for AI agents. It captures the causal chain behind agent decisions — not just LLM calls — and lets you replay from checkpoints, visualize reasoning trees, and detect drift.

**Key features:**
- Local-first: all data stays on your machine
- Causal tracing of decisions, tool calls, and LLM events
- Checkpoint replay and drift detection
- Zero-config auto-patch mode (one env var, no code changes)
- Adapters for LangChain, CrewAI, Pydantic AI, and custom agents
- Self-hosted FastAPI server with React UI

**Install:** `pip install peaky-peek-server && peaky-peek --open`
**Repo:** https://github.com/acailic/agent_debugger
**License:** MIT

### Target Lists

| List | URL | Section to add to |
|------|-----|-------------------|
| awesome-ai | https://github.com/e2b-dev/awesome-ai | Debugging / Observability |
| awesome-llm | https://github.com/Hannibal046/Awesome-LLM | Agent / Debugging |
| awesome-python | https://github.com/vinta/awesome-python | Development Tools / Debugging Tools |
| awesome-ai-agents | https://github.com/e2b-dev/awesome-ai-agents | Debugging / Observability |
| awesome-langchain | https://github.com/kyrolabs/awesome-langchain | Debugging / Tools |
| awesome-react | https://github.com/enaqx/awesome-react | Developer Tools |
| awesome-fastapi | https://github.com/mjhea0/awesome-fastapi | Admin / Developer Tools |
| awesome-devtools | https://github.com/mohebifar/awesome-devtools | (general) |
| awesome-selfhosted | https://github.com/awesome-selfhosted/awesome-selfhosted | Software Development / Debugging |

### Action
For each list, open an issue or PR with the template above. Check the list's contribution guidelines first — some prefer issues, some prefer PRs.

---

## 3. LibHunt & AlternativeTo

### LibHunt (https://libhunt.com)

**Project Name:** Peaky Peek

**Short Description:**
Local-first open-source debugger for AI agents. Capture decisions, replay from checkpoints, and visualize reasoning chains — all on your machine.

**Category:** Developer Tools > Debugging

**Tags:**
ai, debugging, observability, tracing, agents, llm, python, react, fastapi, open-source

**Website:** https://github.com/acailic/agent_debugger

**Why it's different:**
Unlike SaaS observability tools, Peaky Peek keeps all data local, captures the full causal chain (not just LLM calls), and supports checkpoint-based replay with drift detection.

### AlternativeTo (https://alternativeto.net)

**Listing Title:** Peaky Peek

**Description:**
Peaky Peek is a local-first, open-source AI agent debugger. It captures the decision chain behind agent actions — reasoning, tool calls, LLM events — and lets you inspect, replay, and detect drift, all on your machine.

**Categories:**
Developer Tools, Debugging Tools, AI Tools, Open Source Software

**Tags:**
ai-agent, debugging, observability, tracing, llm, python, open-source, local-first, privacy

**Alternatives it competes with (to link):**
- LangSmith (SaaS LLM tracing)
- Phoenix (Arize) (LLM observability)
- Weave (Weights & Biases) (experiment tracking)
- OpenTelemetry (general observability)

**Pros to list:**
- Completely local — no data leaves your machine
- Open source (MIT)
- Zero-config auto-patch mode
- Checkpoint replay with drift detection
- Framework adapters (LangChain, CrewAI, Pydantic AI)
