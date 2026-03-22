# Repo Overview

This page explains the repository in plain language: what it is, what is inside it, what already works, and where it still falls short.

## What This Repo Is

`agent_debugger` is an MVP for tracing and debugging AI agent runs.

The idea is simple: instead of relying on logs alone, record a run as structured events. Once a run is captured that way, you can stream it live, store it, query it later, and eventually replay it.

## Main Goal

The core idea is:

- an agent run should be visible as a meaningful sequence of decisions, model calls, tool activity, errors, and state checkpoints

That is what makes the debugger possible later on:

- session timelines
- decision trees
- tool inspection
- replay
- failure analysis

## Repository Structure

### `agent_debugger_sdk/`

This is the tracing SDK, and it is the heart of the project.

It provides:

- core event types
- `TraceContext`
- tracing decorators
- framework adapters

It matters because it defines the event model and how application code plugs into that model.

### `collector/`

This is the collection layer.

It currently handles:

- event ingestion
- importance scoring
- in-memory buffering for live updates

This is what makes live streaming possible right now.

### `storage/`

This is the persistence layer.

It contains:

- SQLAlchemy models
- repository logic for sessions, events, and checkpoints

This is the right long-term home for session history, even though the runtime path is not fully unified around it yet.

### `api/`

This is the FastAPI application.

It is responsible for:

- session and trace endpoints
- SSE streaming
- startup wiring between the SDK and the event buffer

### `frontend/`

This is the UI layer for the debugger.

It already contains:

- initial hooks for loading traces
- SSE subscription logic
- placeholder visualization components

It is still early. The pieces exist, but they are not assembled into a complete product yet.

## What Works Today

The strongest parts of the repo today are:

- structured event types for agent behavior
- async-safe tracing through `TraceContext`
- decorator-based instrumentation
- framework adapter scaffolding
- live SSE event streaming
- repository models for persistent history

## What Is Still In Progress

The main gaps are:

- live events and persistent history are not fully unified
- session lifecycle exists in both memory and persistence
- the frontend is scaffolded but not assembled into a complete debugger
- replay is represented conceptually more than operationally

## What This Repo Is Good For Right Now

Right now, this codebase is strongest as:

- a tracing model
- a debugging architecture prototype
- a base for building a real agent debugger

It is weaker as:

- a finished developer product
- a fully integrated replay system
- a production-grade observability platform

## What The Repo Needs Next

The next step is not adding more isolated features. It is making the core path coherent:

1. trace a run
2. stream the run live
3. persist the run
4. query the same run later
5. inspect it in one UI

Once that flow works reliably, everything else gets easier.
