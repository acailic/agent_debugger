# ADR-008: Security, Auth & Privacy

**Status:** Accepted
**Date:** 2026-03-23

## Context

Moving from local-only to cloud SaaS requires auth, multi-tenancy, and data privacy controls. Agent traces contain sensitive data: prompts, tool inputs/outputs, LLM responses, and potentially PII from user interactions.

## Decision

### Authentication

| Surface | Method | Details |
|---------|--------|---------|
| **SDK → API** | API key | Prefixed keys (`ad_live_...`, `ad_test_...`). Sent as Bearer token. |
| **Dashboard** | JWT via auth provider | Clerk or Auth0. Email + password, Google OAuth, GitHub OAuth. |
| **Business tier** | SAML SSO | Via auth provider's enterprise features. |

API keys are scoped per environment (live/test) and can be rotated without downtime.

### Multi-tenancy

**Logical isolation** (shared database, tenant_id on all tables):

```
sessions.tenant_id
events.tenant_id  (denormalized for query performance)
checkpoints.tenant_id
```

Every query includes `WHERE tenant_id = :tid`. Enforced at the repository layer, not just the API layer. No ORM query can bypass this.

**Why not physical isolation (separate databases per tenant)?**
- At $5k-20k MRR scale, the operational cost of per-tenant databases is not justified
- Logical isolation with proper enforcement is industry standard (Sentry, PostHog, LaunchDarkly)
- Business tier can optionally get dedicated schema if needed (future consideration)

### Data Privacy

**Configurable redaction pipeline** applied at ingestion time:

| Setting | Behavior | Default |
|---------|----------|---------|
| `redact_prompts` | Replace prompt content with `[REDACTED]`, preserve structure | Off |
| `redact_tool_payloads` | Replace tool input/output with `[REDACTED]` | Off |
| `redact_pii` | Run regex-based PII detection (email, phone, SSN patterns) and replace | Off |
| `max_payload_size` | Truncate payloads exceeding N KB | 100KB |

Redaction is **irreversible and applied before storage**. We never store the unredacted version. This is a deliberate trade-off: some debugging utility is lost, but data risk is eliminated.

### Encryption

- **In transit**: TLS 1.3 for all API communication
- **At rest**: Database-level encryption (PostgreSQL TDE or AWS RDS encryption)
- **S3 payloads**: Server-side encryption (SSE-S3)
- **API keys**: Hashed with bcrypt in database, only shown once at creation

### Data Retention

| Tier | Retention | After Expiry |
|------|-----------|-------------|
| Developer | 30 days | Soft delete → hard delete after 7-day grace |
| Team | 90 days | Soft delete → hard delete after 7-day grace |
| Business | 1 year (configurable) | Configurable archive vs delete |

Retention is enforced by a daily background job that marks expired sessions for deletion.

### Audit Log (Business tier)

Track: who accessed which session, API key usage, configuration changes, team member additions/removals. Stored separately from trace data with its own retention policy (minimum 1 year).

## Assumptions

- At the $5k-20k MRR scale, we will have < 500 tenants. Logical isolation handles this.
- Most customers will not enable redaction (debugging requires seeing the data). But enterprise customers will require it.
- GDPR compliance: data deletion on account closure, data export on request. Both achievable with tenant_id-based queries.

## Consequences

- tenant_id must be added to all database models (schema migration)
- Repository layer must enforce tenant isolation with no bypass
- API key management endpoints needed (create, list, rotate, revoke)
- Redaction pipeline runs on every ingested event (performance consideration)
- Must implement soft-delete and retention job before cloud launch
- Auth provider integration needed before cloud launch (Clerk recommended for speed)
