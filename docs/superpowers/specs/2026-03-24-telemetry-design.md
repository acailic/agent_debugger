# User Analytics Dashboard Design

**Date:** 2026-03-24
**Status:** Draft
**Scope:** Analytics tab for users to view their own debugging efficiency gains

## Overview

Add a dedicated Analytics tab that shows users how much time they've saved using Peaky Peek's features. Uses implicit tracking only (clicks, feature usage) - no explicit ratings or external services.

## Goals

- Show users their debugging efficiency gains
- Encourage feature adoption through visible metrics
- Maintain local-first privacy (no external analytics services)

## Non-Goals

- Team-level aggregation (each machine separate)
- Internal product analytics (not tracking adoption funnels)
- External telemetry or crash reporting

## Approach

SQLite-based local analytics database separate from trace storage. API writes events to `analytics.db`, frontend queries aggregated stats via new endpoint.

## Events to Track

| Event | When Triggered | Properties |
|-------|---------------|------------|
| `session_created` | New debug session started | `session_id`, `agent_name` |
| `why_button_clicked` | User clicks "Why Did It Fail?" | `session_id`, `decision_id` |
| `failure_matched` | Failure Memory finds similar past failure | `session_id`, `match_count` |
| `replay_started` | User starts replay | `session_id`, `mode` (full/focus/failure) |
| `replay_highlights_used` | User views AI-curated highlights | `session_id` |
| `behavior_alert_viewed` | User views drift alert | `agent_name`, `alert_type` |
| `nl_query_made` | Natural language debug query | `session_id` (optional) |
| `search_performed` | Trace search executed | `query_type`, `has_results` |

## Storage Schema

New `analytics.db` SQLite database:

```sql
-- Raw events (append-only log)
CREATE TABLE analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    session_id TEXT,
    agent_name TEXT,
    properties TEXT,  -- JSON blob for flexible event data
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_events_type ON analytics_events(event_type);
CREATE INDEX idx_events_created ON analytics_events(created_at);
CREATE INDEX idx_events_session ON analytics_events(session_id);

-- Pre-computed daily aggregates (for fast dashboard loads)
CREATE TABLE daily_aggregates (
    date TEXT NOT NULL PRIMARY KEY,
    sessions_created INTEGER DEFAULT 0,
    why_button_clicks INTEGER DEFAULT 0,
    failures_matched INTEGER DEFAULT 0,
    replays_started INTEGER DEFAULT 0,
    replay_highlights_used INTEGER DEFAULT 0,
    behavior_alerts_viewed INTEGER DEFAULT 0,
    nl_queries_made INTEGER DEFAULT 0,
    searches_performed INTEGER DEFAULT 0
);
```

Daily aggregates enable fast queries for 90-day range (90 rows vs thousands of events).

## API Endpoints

### GET `/api/analytics`

Query params:
- `range`: `7d` | `30d` | `90d` (default: `30d`)

Response:
```json
{
  "range": "30d",
  "period_start": "2026-02-22",
  "period_end": "2026-03-24",
  "metrics": {
    "sessions_created": 47,
    "why_button_clicks": 38,
    "failures_matched": 12,
    "replay_highlights_used": 23,
    "nl_queries_made": 8,
    "searches_performed": 31
  },
  "derived": {
    "adoption_rate": {
      "why_button": 0.81,
      "failure_memory": 0.26,
      "replay_highlights": 0.49
    },
    "estimated_time_saved_minutes": 285
  },
  "daily_breakdown": [
    {"date": "2026-03-24", "sessions": 3, "clicks": 2}
  ]
}
```

### POST `/api/analytics/events`

Internal endpoint for recording events (called by other API routes, not exposed to frontend directly).

Request:
```json
{
  "event_type": "why_button_clicked",
  "session_id": "abc123",
  "properties": {"decision_id": "dec_45"}
}
```

## Time Saved Calculation

Based on advertised efficiency gains:

| Feature | Time Saved Per Use |
|---------|-------------------|
| Why Button | 14.5 min (15min → 30sec) |
| Failure Memory | 18 min (20min → 2min) |
| Replay Highlights | 8.5 min (10min → 1.5min) |

Formula: `sum(event_count × time_saved_per_event)`

## Frontend Dashboard

### Layout

```
┌─────────────────────────────────────────────────────────┐
│  [7 days] [30 days] [90 days]     ← Time range selector │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│   │ 47          │  │ 285 min     │  │ 38          │    │
│   │ Sessions    │  │ Time Saved  │  │ Why Clicks  │    │
│   └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  Feature Adoption                                       │
│   ████████████████████░░░░  Why Button      81%        │
│   ██████████░░░░░░░░░░░░░░  Replay Highlights 49%      │
│   █████░░░░░░░░░░░░░░░░░░░  Failure Memory   26%       │
│   ███░░░░░░░░░░░░░░░░░░░░░░  NL Queries      17%       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   Sessions over time (sparkline chart)                  │
│   ▁▂▃▅▇▅▃▂▁▂▄▆▇▆▄▃▂▁                                   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Components

- Time range selector (7/30/90 day toggle buttons)
- Three summary stat cards (Sessions, Time Saved, Why Clicks)
- Feature adoption bar chart (horizontal bars with percentages)
- Activity sparkline (optional, shows daily session counts)

### Integration

- Add "Analytics" tab to main navigation
- Fetch data on mount, refresh when time range changes
- Cache response for 5 minutes (avoid re-fetching on tab switch)
- Show "Analytics unavailable" if database fails

## File Changes

### New Files

| File | Purpose |
|------|---------|
| `api/analytics_routes.py` | API endpoints for analytics |
| `api/analytics_db.py` | SQLite connection and queries |
| `storage/analytics_migrations.py` | Schema setup for analytics.db |
| `frontend/src/components/AnalyticsPanel.tsx` | Dashboard UI component |

### Modified Files

| File | Change |
|------|--------|
| `frontend/src/api/client.ts` | Add `getAnalytics(range)` |
| `frontend/src/types/index.ts` | Add `AnalyticsResponse` type |
| `frontend/src/App.tsx` | Add Analytics tab/route |
| `api/main.py` | Mount analytics routes |

## Event Recording Locations

| Location | Event |
|----------|-------|
| `api/session_routes.py` | `session_created` |
| `api/trace_routes.py` | `why_button_clicked`, `failure_matched` |
| `api/replay_routes.py` | `replay_started`, `replay_highlights_used` |
| `api/trace_routes.py` | `search_performed`, `nl_query_made` |
| `collector/live_monitor.py` | `behavior_alert_viewed` |

## Error Handling

- Analytics writes are fire-and-forget (don't block API responses)
- If analytics.db is locked/corrupted, log warning and continue
- Dashboard shows "Analytics unavailable" if database fails
- No external network calls - analytics failure is isolated

## Privacy Considerations

- All data stays local (SQLite on user's machine)
- No external analytics services (PostHog, Amplitude, etc.)
- No PII in event properties
- User can delete `analytics.db` to clear history
- Analytics is opt-out via configuration (can disable entirely)

## Alternatives Considered

1. **In-memory + main DB**: Simpler but mixes concerns, harder to optimize
2. **DuckDB**: Overkill for current scale, added complexity
3. **External analytics**: Violates local-first privacy commitment

## Open Questions

None - design is complete and approved.
