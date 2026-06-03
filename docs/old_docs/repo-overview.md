# Repo Overview

This page explains the repository in plain language: what it is, what is inside it, what already works, and where it still falls short.

## What This Repo Is

`agent_debugger` is a working trace debugger for AI agent runs.

The idea is simple: instead of relying on logs alone, record a run as structured events. Once a run is captured that way, you can stream it live, store it, query it later, analyze it, and replay it from checkpoints.

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

It handles:

- event ingestion
- importance scoring
- in-memory buffering for live updates
- replay helpers
- adaptive trace intelligence

This is what makes live streaming possible right now.

### `benchmarks/`

This is the reusable scenario layer for regression tests and demo data.

It contains:

- seeded benchmark sessions
- reusable scenario runners for tests
- stable session IDs for local demo seeding

### `storage/`

This is the persistence layer.

It contains:

- SQLAlchemy models
- repository logic for sessions, events, and checkpoints

This is the durable source of truth for session history.

### `api/`

This is the FastAPI application.

It is responsible for:

- session, trace, analysis, and replay endpoints
- SSE streaming
- startup wiring between the SDK and the event buffer
- startup wiring between the SDK and database-backed persistence

### `auth/`

This is the start of the cloud security layer.

It currently contains:

- API key generation and bcrypt hashing
- auth-related ORM models
- FastAPI helpers for resolving a tenant from a bearer token

Important:

- this is progress, but not full multi-tenant enforcement yet

### `redaction/`

This is the privacy layer.

It currently contains:

- configurable prompt redaction
- configurable tool payload redaction
- regex-based PII scrubbing

Important:

- the pipeline exists and is tested
- it is not yet wired into the ingestion path

### `frontend/`

This is the UI layer for the debugger.

It contains:

- session loading
- replay controls
- timeline and tree views
- tool and LLM inspectors
- event detail and analysis views

It is still early as a product, but it is no longer a placeholder shell.

### `scripts/`

This is the operational helper layer.

It currently includes:

- `scripts/seed_demo_sessions.py` for populating the local database with benchmark sessions

## What Works Today

The strongest parts of the repo today are:

- structured event types for agent behavior
- async-safe tracing through `TraceContext`
- decorator-based instrumentation
- framework adapter scaffolding
- `agent_debugger.init()` for local/cloud configuration
- live SSE event streaming
- repository-backed persistent history
- adaptive event ranking and failure clustering
- checkpoint-aware replay endpoints
- a usable frontend debugger surface
- benchmark/demo seed coverage
- API key and redaction primitives for the next cloud step

## What Is Still In Progress

The main gaps are:

- execution restoration is shallower than the replay model suggests
- cross-session clustering is still limited
- auth and privacy work exists, but is not wired end to end
- tenant isolation is not enforced in the repository yet
- SDK cloud transport is not finished
- retention and deployment hardening are still missing
- docs and legacy helper modules still need periodic cleanup

## What This Repo Is Good For Right Now

Right now, this codebase is strongest as:

- a local debugger for agent traces
- a research-informed observability surface
- a base for deeper replay, adaptive evaluation, and cloud hardening

It is weaker as:

- a production multi-tenant platform
- a cloud-hosted debugger with enforced tenant boundaries
- a fully restorable execution debugger
- a production-grade observability platform

## What The Repo Needs Next

The next step is not redoing the contract layer. It is deepening the product around the working core:

1. trace a run
2. stream the run live
3. persist the run
4. query the same run later
5. analyze and replay it in one UI

That flow is now real. The next leverage is finishing the cloud/security path, then deepening replay semantics and cross-session analysis.
