---
title: API Reference
description: REST API endpoints and routes documentation
---

# API Reference

Peaky Peek provides a comprehensive REST API for querying sessions, traces, replay, search, analytics, and more.

## Base URL

```
http://localhost:8000
```

## Authentication

API key authentication via `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/api/sessions
```

## Routers Overview

The API is organized into 11 routers:

1. **Sessions** — Session CRUD operations
2. **Traces** — Trace event queries
3. **Replay** — Time-travel and checkpoint replay
4. **Search** — Cross-session trace search
5. **Analytics** — Aggregated metrics and insights
6. **Cost** — Token usage and cost tracking
7. **Comparison** — Session comparison
8. **Entity** — Entity extraction and tracking
9. **Policy** — Prompt policy analysis
10. **Cross-Session** — Multi-agent coordination
11. **Auth** — API key management

## Session Routes

### List Sessions

```http
GET /api/sessions
```

Query parameters:
- `limit` — Number of sessions to return (default: 50)
- `offset` — Pagination offset (default: 0)
- `agent_name` — Filter by agent name
- `framework` — Filter by framework
- `status` — Filter by status (running, completed, error)

**Response:**
```json
{
  "sessions": [
    {
      "id": "uuid",
      "agent_name": "weather_agent",
      "framework": "custom",
      "started_at": "2024-01-01T00:00:00Z",
      "ended_at": "2024-01-01T00:00:05Z",
      "status": "completed",
      "total_tokens": 1000,
      "total_cost_usd": 0.01,
      "tool_calls": 5,
      "llm_calls": 2,
      "errors": 0
    }
  ],
  "total": 100
}
```

### Get Session

```http
GET /api/sessions/{session_id}
```

**Response:**
```json
{
  "id": "uuid",
  "agent_name": "weather_agent",
  "framework": "custom",
  "started_at": "2024-01-01T00:00:00Z",
  "ended_at": "2024-01-01T00:00:05Z",
  "status": "completed",
  "total_tokens": 1000,
  "total_cost_usd": 0.01,
  "tool_calls": 5,
  "llm_calls": 2,
  "errors": 0,
  "config": {},
  "tags": []
}
```

### Delete Session

```http
DELETE /api/sessions/{session_id}
```

## Trace Routes

### Get Session Traces

```http
GET /api/sessions/{session_id}/traces
```

Query parameters:
- `event_type` — Filter by event type
- `limit` — Number of events to return

**Response:**
```json
{
  "events": [
    {
      "id": "uuid",
      "session_id": "uuid",
      "parent_id": null,
      "event_type": "agent_start",
      "timestamp": "2024-01-01T00:00:00Z",
      "name": "weather_agent",
      "data": {},
      "metadata": {},
      "importance": 0.5,
      "sequence": 0
    }
  ]
}
```

### Get Decision Tree

```http
GET /api/sessions/{session_id}/tree
```

**Response:**
```json
{
  "nodes": [
    {
      "id": "uuid",
      "event_type": "decision",
      "name": "call_weather_api",
      "children": ["uuid2", "uuid3"]
    }
  ]
}
```

### Get Normalized Trace Bundle

```http
GET /api/sessions/{session_id}/trace
```

Returns a normalized bundle with all trace data, analysis, and metadata.

## Replay Routes

### Get Checkpoints

```http
GET /api/sessions/{session_id}/checkpoints
```

**Response:**
```json
{
  "checkpoints": [
    {
      "id": "uuid",
      "session_id": "uuid",
      "event_id": "uuid",
      "sequence": 5,
      "state": {},
      "timestamp": "2024-01-01T00:00:05Z",
      "importance": 0.8
    }
  ]
}
```

### Start Replay

```http
POST /api/sessions/{session_id}/replay
```

Request body:
```json
{
  "from_event_id": "uuid",
  "breakpoint_rules": [
    {
      "event_type": "error",
      "tool_name": null,
      "confidence_min": null,
      "safety_outcome": null
    }
  ]
}
```

## Search Routes

### Search Traces

```http
POST /api/traces/search
```

Request body:
```json
{
  "query": "weather API failure",
  "event_types": ["error", "tool_result"],
  "limit": 50
}
```

**Response:**
```json
{
  "results": [
    {
      "event_id": "uuid",
      "session_id": "uuid",
      "event_type": "error",
      "data": {},
      "score": 0.95
    }
  ]
}
```

## Analytics Routes

### Get Session Analytics

```http
GET /api/sessions/{session_id}/analytics
```

**Response:**
```json
{
  "summary": {
    "total_events": 100,
    "decisions": 20,
    "tool_calls": 30,
    "llm_calls": 10,
    "errors": 2
  },
  "rankings": [
    {
      "event_id": "uuid",
      "score": 0.9,
      "reason": "High error impact"
    }
  ],
  "clusters": [
    {
      "cluster_id": "uuid",
      "events": ["uuid1", "uuid2"],
      "description": "API timeout pattern"
    }
  ]
}
```

### Get Global Analytics

```http
GET /api/analytics
```

Query parameters:
- `start_date` — Start date filter
- `end_date` — End date filter

## Cost Routes

### Get Session Cost

```http
GET /api/sessions/{session_id}/cost
```

**Response:**
```json
{
  "total_cost_usd": 0.05,
  "total_tokens": 5000,
  "by_model": {
    "gpt-4o": {
      "input_tokens": 3000,
      "output_tokens": 2000,
      "cost_usd": 0.05
    }
  }
}
```

### Get Cost Summary

```http
GET /api/cost/summary
```

Query parameters:
- `start_date` — Start date filter
- `end_date` — End date filter

## Comparison Routes

### Compare Sessions

```http
POST /api/compare
```

Request body:
```json
{
  "session_id_1": "uuid1",
  "session_id_2": "uuid2"
}
```

**Response:**
```json
{
  "differences": [
    {
      "field": "tool_calls",
      "session_1": 5,
      "session_2": 3,
      "diff": 2
    }
  ],
  "unique_to_session_1": [...],
  "unique_to_session_2": [...]
}
```

## Entity Routes

### Extract Entities

```http
POST /api/sessions/{session_id}/entities
```

**Response:**
```json
{
  "entities": [
    {
      "name": "Seattle",
      "type": "location",
      "count": 5,
      "first_seen": "uuid",
      "events": ["uuid1", "uuid2"]
    }
  ]
}
```

## Policy Routes

### Get Policy Analysis

```http
GET /api/sessions/{session_id}/policy
```

**Response:**
```json
{
  "policies": [
    {
      "name": "safety_check",
      "violations": 0,
      "refusals": 1,
      "parameters": {}
    }
  ]
}
```

## Cross-Session Routes

### Get Multi-Agent Coordination

```http
GET /api/sessions/{session_id}/cross-session
```

**Response:**
```json
{
  "speakers": [
    {
      "name": "planner",
      "turns": 10,
      "tools_used": ["search", "analyze"]
    }
  ],
  "topology": "hierarchical"
}
```

## Auth Routes

### Create API Key

```http
POST /api/auth/keys
```

Request body:
```json
{
  "name": "My Key",
  "scopes": ["read", "write"]
}
```

**Response:**
```json
{
  "key_id": "uuid",
  "api_key": "ad_live_...",
  "name": "My Key",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### List API Keys

```http
GET /api/auth/keys
```

### Delete API Key

```http
DELETE /api/auth/keys/{key_id}
```

## System Routes

### Health Check

```http
GET /api/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### System Info

```http
GET /api/system/info
```

**Response:**
```json
{
  "version": "1.0.0",
  "python_version": "3.11.0",
  "database": "sqlite"
}
```

## Streaming

### Server-Sent Events (SSE)

```http
GET /api/sessions/{session_id}/stream
```

Subscribe to live events for a session. Returns `text/event-stream` with real-time event updates.

## Error Responses

All endpoints return consistent error responses:

```json
{
  "detail": "Error message",
  "error": "error_code",
  "status": 400
}
```

Common error codes:
- `session_not_found` — Session does not exist
- `invalid_request` — Invalid request parameters
- `unauthorized` — Missing or invalid API key
- `internal_error` — Server error

## Rate Limiting

API rate limits (if configured):

- 100 requests per minute per API key
- 1000 requests per hour per API key

Rate limit headers are included in responses:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
```

## SDK Client

### Python SDK

```python
from agent_debugger_sdk import TraceContext, init

init()

async with TraceContext(agent_name="my_agent") as ctx:
    await ctx.record_decision(
        reasoning="User asked for help",
        confidence=0.9,
        chosen_action="provide_answer",
    )
```

### HTTP Client

```bash
# List sessions
curl http://localhost:8000/api/sessions

# Get session details
curl http://localhost:8000/api/sessions/{session_id}

# Search traces
curl -X POST http://localhost:8000/api/traces/search \
  -H "Content-Type: application/json" \
  -d '{"query": "error", "limit": 10}'
```

## Next Steps

- [Getting Started](getting-started.md) — 5-minute quickstart
- [Integrations](integrations.md) — Framework-specific setup
- [Configuration](configuration.md) — Configuration options
