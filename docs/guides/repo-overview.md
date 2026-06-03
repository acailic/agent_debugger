# Repo Overview

This page explains the repository in plain language: what it is, what is inside it, and what already works.

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

This is the security layer.

It currently contains:

- API key generation and bcrypt hashing
- auth-related ORM models
- FastAPI helpers for resolving a tenant from a bearer token

### `redaction/`

This is the privacy layer.

It currently contains:

- configurable prompt redaction
- configurable tool payload redaction
- regex-based PII scrubbing

The pipeline is wired into the event persistence path.

### `frontend/`

This is the UI layer for the debugger.

It contains:

- session loading
- replay controls
- timeline and tree views
- tool and LLM inspectors
- event detail and analysis views

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
- `init()` for local/cloud configuration
- live SSE event streaming
- repository-backed persistent history
- adaptive event ranking and failure clustering
- checkpoint-aware replay endpoints
- a usable frontend debugger surface
- benchmark/demo seed coverage
- API key and redaction primitives for cloud deployment
- tenant isolation enforced in the repository

## What This Repo Is Good For Right Now

Right now, this codebase is strongest as:

- a local debugger for agent traces
- a research-informed observability surface
- a base for deeper replay, adaptive evaluation, and cloud hardening

It is weaker as:

- a production multi-tenant platform
- a fully restorable execution debugger
