# ADR-005: Architecture for Scale

**Status:** Accepted
**Date:** 2026-03-23

## Context

The current architecture (SQLite + in-memory EventBuffer + single FastAPI process) works well for local debugging. Cloud deployment needs horizontal scaling, durable event fan-out, and separation of ingestion from analysis.

## Decision

Maintain the current architecture for local/self-hosted mode. Add a scale layer for cloud mode. Same codebase, different configuration.

### Local Mode (Unchanged)

```
Agent SDK → HTTP POST → FastAPI → EventBuffer (in-memory) → SSE
                                → SQLite (persistence)
```

Single process. Zero infrastructure. Works offline.

### Cloud Mode

```
Agent SDK → HTTP POST → API Gateway → Ingestion API
                                          ↓
                                    Redis Streams (event queue)
                                     ↓              ↓
                              Worker (persist)   Worker (analyze)
                                  ↓                  ↓
                             PostgreSQL           Redis pub/sub
                             + S3 (payloads)         ↓
                                  ↓              SSE/WebSocket
                             Query API  ←←←←←←  Frontend
```

### Key Components

| Component | Local | Cloud | Why |
|-----------|-------|-------|-----|
| **Database** | SQLite | PostgreSQL | SQLite is single-writer; PG scales |
| **Event buffer** | In-memory EventBuffer | Redis Streams | Durable, multi-consumer, backpressure |
| **Live fan-out** | In-memory → SSE | Redis pub/sub → SSE | Multi-process fan-out |
| **Large payloads** | Stored in event JSON | S3 with reference pointer | LLM request/response bodies can be 100KB+ |
| **Analysis** | Inline in request | Background worker | Don't block ingestion on scoring/clustering |
| **Auth** | None (local) | API key (SDK) + JWT (dashboard) | Required for multi-tenancy |

### Migration Path

The abstraction layer that makes this work already exists partially:

1. **Repository pattern**: `storage/repository.py` already abstracts database access. Add PostgreSQL dialect support.
2. **EventBuffer interface**: Extract interface, implement Redis-backed version.
3. **Analysis pipeline**: `collector/intelligence.py` already has the logic. Wrap in a worker that reads from Redis Streams.

### Why Not Over-Engineer From Day One

- Local mode must remain zero-dependency (no Redis, no PostgreSQL)
- Cloud infrastructure cost should start near zero and scale with users
- The same API code should run both modes via config, not separate codebases

## Technology Choices

| Choice | Decision | Alternative Considered | Reason |
|--------|----------|----------------------|--------|
| Queue | Redis Streams | Kafka, RabbitMQ, NATS | Redis is already useful for pub/sub and caching. Streams adds durable queues without new infrastructure. Kafka is overkill at this scale. |
| Database | PostgreSQL | MySQL, CockroachDB | Industry standard, excellent JSON support, well-supported by SQLAlchemy |
| Object storage | S3 (or MinIO for self-hosted) | Database BLOBs | LLM payloads can be large. S3 is cheaper and doesn't bloat the database. |
| Hosting | Fly.io or Railway initially | AWS/GCP | Lower ops overhead for small team. Can migrate to AWS later. |

## Scaling Targets

| Metric | Local | Cloud (initial) | Cloud (at $20k MRR) |
|--------|-------|-----------------|---------------------|
| Events/second | 10-100 | 500 | 5,000 |
| Concurrent sessions | 1-5 | 50 | 500 |
| Storage | Local disk | 100GB PG + S3 | 1TB PG + S3 |
| API instances | 1 | 2 | 4-8 |
| Workers | 0 (inline) | 2 | 4-8 |

## Consequences

- Must define clear interface boundaries between local and cloud implementations
- Must not introduce cloud dependencies into the local path
- Redis becomes a critical dependency for cloud mode
- Need database migration tooling (Alembic) from day one for cloud
- S3 reference pattern means payloads are eventually consistent (acceptable for debugging tool)
