# Intro

`agent_debugger` is a trace-first debugger for AI agents.

Instead of trying to understand an agent run from logs alone, it records the run as structured events. That gives you a timeline, a tree of parent and child actions, replay inputs, live streaming, and later analysis over the same captured run.

## What You Get

Today the repo is strongest at the local debugger loop:

1. run the API
2. instrument an agent with the SDK
3. inspect sessions, events, checkpoints, and replay data

The main things you can inspect are:

- agent start and end
- decisions and reasoning
- LLM requests and responses
- tool calls and results
- errors
- checkpoints
- safety and policy events

## Who This Is For

This project is useful if you want to:

- understand why an agent chose a tool or answer
- inspect the sequence of model calls and tool calls
- debug failures with more structure than raw logs
- build replay, evaluation, or safety workflows on top of captured traces

## What Works Well Now

- `TraceContext` for explicit tracing
- decorators for lightweight instrumentation
- framework adapters for PydanticAI and LangChain
- FastAPI routes for sessions, traces, analysis, replay, and streaming
- a React frontend that reads the normalized backend trace bundle

## What To Expect

The local path is the clearest supported workflow today.

Cloud-oriented configuration, auth, tenant isolation, and privacy work exist in the repo, but they are still being hardened and finished. The docs in this folder try to separate:

- what works end to end now
- what exists but is still partial
- what is still planned

## Start Here

- [Integration](./integration.md): how to instrument your code
- [Progress](./progress.md): what is done and what is still partial
- [How It Works](./how-it-works.md): the runtime path from SDK to UI
- [Architecture](./architecture.md): the major layers and modules
