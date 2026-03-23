# ADR-002: Deployment Model

**Status:** Accepted
**Date:** 2026-03-23

## Context

Developer tools have a proven adoption funnel: open-source builds trust, cloud provides convenience and revenue. Examples: Sentry, PostHog, Grafana, Airbyte. Pure SaaS developer tools face adoption friction. Pure open-source struggles to monetize.

## Decision

**Open-source SDK + hosted cloud SaaS.** The hybrid model.

### How It Works

The SDK (`peaky-peek` on PyPI) is open-source under MIT. Developers install it, instrument their agents, and events flow to either:

1. **Local mode** (free): Events go to a local collector/SQLite. Full debugger UI runs on localhost. Single user. No cloud dependency.
2. **Cloud mode** (paid): Events go to our hosted API. Team features, persistent storage, collaboration, longer retention.

### Configuration

```
# Local mode (default, no config needed)
pip install peaky-peek
# Sends events to a local server when one is running

# Cloud mode (one env var)
export AGENT_DEBUGGER_API_KEY=ad_live_...
# Events now flow to cloud
```

## Reasoning

| Model | Adoption | Revenue | Trust | Maintenance |
|-------|----------|---------|-------|-------------|
| SaaS only | Low friction but low trust | Direct | Low until proven | Single codebase |
| Self-hosted only | High trust, high friction | None / support-based | High | Single codebase |
| **Hybrid** | **High trust + low friction** | **Cloud subscriptions** | **High** | **Two deployment targets** |

The maintenance cost of two deployment targets is real but manageable because:
- The SDK is identical in both modes (just different endpoint URL)
- The API server is the same code, just different config (SQLite vs PostgreSQL, local vs cloud auth)
- The frontend is identical, just different data source

## Consequences

- Must keep local experience excellent (not a crippled free tier)
- Cloud must offer clear value beyond "same thing but hosted" (teams, retention, collaboration)
- SDK must work offline and not phone home without explicit opt-in
- MIT keeps adoption friction low and matches the repo's current licensing
- Cloud-only features can still remain separate product decisions without changing the SDK license
