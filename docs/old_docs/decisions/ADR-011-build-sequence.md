# ADR-011: Build Sequence

**Status:** Accepted
**Date:** 2026-03-23

## Context

We have a working local MVP. We need to get to first paying customers within 2-3 months. The build sequence must balance: shipping fast, not breaking what works, and building the right things in the right order.

## Decision

Three phases over ~10 weeks. Each phase has a clear exit milestone.

### Phase 1: Cloud-Ready Backend + Polished SDK (Weeks 1-4)

**Goal**: One person can sign up, instrument their agent, and see traces in a cloud-hosted debugger.

**SDK Work:**
- [ ] Implement `agent_debugger.init()` auto-configuration entry point
- [ ] Add LangChain auto-instrumentation (patch callback system)
- [ ] Graceful degradation (SDK never crashes the user's agent)
- [ ] PyPI packaging as `agent-debugger`
- [ ] Environment-based configuration (API key, endpoint, sampling)
- [ ] Harden existing PydanticAI adapter

**Backend Work:**
- [ ] PostgreSQL support via SQLAlchemy (alongside existing SQLite)
- [ ] Database migrations with Alembic
- [ ] API key authentication for SDK ingestion
- [ ] tenant_id on all models, enforced at repository layer
- [ ] Redis-backed EventBuffer for cloud (alongside in-memory for local)
- [ ] S3 storage for large payloads (optional, graceful fallback)
- [ ] Background worker for analysis (scoring, clustering)
- [ ] Health check and readiness endpoints

**Frontend Work:**
- [ ] Polish the three core workflows (investigate failure, understand decision, monitor live)
- [ ] Session virtualization for large traces (10k+ events)
- [ ] Shareable session URLs
- [ ] Dark theme polish

**Exit milestone**: Deploy to Fly.io/Railway. One test user can `pip install agent-debugger`, set API key, and see traces in cloud UI.

### Phase 2: Auth + Teams + Landing Page (Weeks 5-7)

**Goal**: Multiple people can sign up, form teams, and use the product together. There is a public landing page.

**Auth & Billing:**
- [ ] Clerk integration (signup, login, Google/GitHub OAuth)
- [ ] API key management UI (create, list, rotate, revoke)
- [ ] Stripe integration (Developer and Team tiers)
- [ ] Soft event volume limits with friendly nudges
- [ ] Data retention enforcement (background job)

**Team Features:**
- [ ] Team creation and member management
- [ ] Shared session access within team
- [ ] Team-level API keys
- [ ] Basic usage dashboard (events ingested, sessions, storage)

**Marketing & Landing:**
- [ ] Landing page (positioning, demo GIF, pricing, getting started)
- [ ] Documentation site (quickstart, SDK reference, adapters guide)
- [ ] "Agent Debugger vs LangSmith" comparison page
- [ ] Blog post: "Why agent debugging is different from LLM tracing"

**Exit milestone**: Landing page is live. Signup → first trace in under 5 minutes. Team creation works. Stripe accepts payments.

### Phase 3: Beta Launch + Feedback Loop (Weeks 8-10)

**Goal**: First paying customers. Active feedback collection. Rapid iteration.

**Launch Activities:**
- [ ] Private beta invite to 20-50 developers (LangChain Discord, Twitter, HN)
- [ ] Public beta announcement
- [ ] CrewAI adapter (second framework)
- [ ] Feedback collection system (in-app + email)
- [ ] Bug fix velocity target: critical bugs fixed within 24 hours

**Product Iteration:**
- [ ] Prioritize based on beta feedback
- [ ] Add PII redaction controls (before enterprise interest)
- [ ] Improve decision tree visualization based on real-world traces
- [ ] Add session comparison (side-by-side debugging of two runs)
- [ ] Performance optimization based on real usage patterns

**Growth:**
- [ ] Monitor conversion funnel: signup → instrument → active user → paid
- [ ] Weekly usage metrics review
- [ ] Direct outreach to active free users about paid tiers

**Exit milestone**: 10+ paying customers. Clear signal on what matters most to users.

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Cloud infra delays | Start with Railway/Fly.io (managed, fast setup). Don't over-engineer infra. |
| SDK compatibility issues | Test against pinned framework versions. Maintain compatibility matrix. |
| Low initial adoption | Open-source SDK means adoption can grow organically. Don't gate useful features. |
| LangSmith adds better agent debugging | Our depth advantage takes months to replicate. Move fast. |
| Scope creep | This ADR IS the scope. If it is not in the 10-week plan, it waits. |

## What Is Explicitly Deferred

- AutoGen adapter (after Phase 3)
- VS Code extension
- SAML SSO (Business tier)
- Dedicated database per tenant
- Audit logging
- Custom retention policies
- Mobile support
- Self-hosted enterprise distribution

## Consequences

- Must ship Phase 1 in 4 weeks. This is tight but achievable because the core is already built.
- Phase 2 requires auth provider and Stripe integration -- these have learning curves.
- Phase 3 success depends on reaching the right beta users. Marketing effort starts in Phase 2.
- Each phase builds on the previous. No skipping.
