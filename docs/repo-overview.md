# Repo Overview

This document explains the repository in plain terms: what it is, what is inside it, what currently works, and what is still incomplete.

## What This Repo Is

`agent_debugger` is an MVP for tracing and debugging AI agent runs.

The repo is trying to make agent behavior inspectable by turning a run into structured events instead of relying only on logs. Those events can then be streamed, stored, queried, and eventually replayed.

## Main Goal

The project is built around one core idea:

- an agent run should be visible as a meaningful sequence of decisions, model calls, tool activity, errors, and state checkpoints

That is what makes later UI features possible:

- session timelines
- decision trees
- tool inspection
- replay
- failure analysis

## Repository Structure

### `agent_debugger_sdk/`

This is the tracing SDK.

It provides:

- core event types
- `TraceContext`
- tracing decorators
- framework adapters

This is the most important part of the repo because it defines the event model and the instrumentation surface.

### `collector/`

This is the event collection layer.

It currently handles:

- event ingestion
- importance scoring
- in-memory buffering for live updates

This is what powers the live stream path.

### `storage/`

This is the persistence layer.

It contains:

- SQLAlchemy models
- repository logic for sessions, events, and checkpoints

This is the right long-term source of truth, even though the runtime path is not fully unified around it yet.

### `api/`

This is the FastAPI application.

It is responsible for:

- session and trace endpoints
- SSE streaming
- startup wiring between the SDK and the event buffer

### `frontend/`

This is the UI layer.

It already contains:

- initial hooks for loading traces
- SSE subscription logic
- placeholder visualization components

It does not yet provide a finished debugging experience.

## What Works Today

The repo already has a useful base:

- structured event types for agent behavior
- async-safe tracing through `TraceContext`
- decorator-based instrumentation
- framework adapter scaffolding
- live SSE event streaming
- repository models for persistent history

## What Is Still In Progress

The MVP is not fully closed end to end yet.

The main gaps are:

- live events and persistent history are not fully unified
- session lifecycle exists in both memory and persistence
- the frontend is scaffolded but not assembled into a complete debugger
- replay is represented conceptually more than operationally

## What This Repo Is Good For Right Now

Right now, the repo is strongest as:

- a tracing model
- a debugging architecture prototype
- a base for building a real agent debugger

It is weaker as:

- a finished developer product
- a fully integrated replay system
- a production-grade observability platform

## What The Repo Needs Next

The next maturity step is not adding more isolated features. It is making the core path coherent:

1. trace a run
2. stream the run live
3. persist the run
4. query the same run later
5. inspect it in one UI

Once that flow is reliable, the repo becomes much easier to extend.
