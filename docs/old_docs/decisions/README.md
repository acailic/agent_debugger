# Architecture Decision Records

This directory contains architectural decisions for the Agent Debugger product evolution from local MVP to revenue-generating SaaS.

Each decision is numbered and self-contained. Decisions can be superseded but not deleted.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| 001 | [Product Positioning](./ADR-001-product-positioning.md) | Under Review — test positioning variants with beta users |
| 002 | [Deployment Model](./ADR-002-deployment-model.md) | **Accepted** |
| 003 | [Pricing Strategy](./ADR-003-pricing-strategy.md) | Under Review — validate price points, consider $19 + freemium |
| 004 | [Target Users & Framework Priority](./ADR-004-target-users-framework-priority.md) | **Accepted** |
| 005 | [Architecture for Scale](./ADR-005-architecture-for-scale.md) | **Accepted** |
| 006 | [SDK Distribution & Developer Experience](./ADR-006-sdk-distribution-dx.md) | **Accepted** |
| 007 | [Replay Fidelity Strategy](./ADR-007-replay-fidelity.md) | Under Review — test user reaction, consider cached replay mode |
| 008 | [Security, Auth & Privacy](./ADR-008-security-auth-privacy.md) | **Accepted** |
| 009 | [Frontend Strategy](./ADR-009-frontend-strategy.md) | Under Review — reconsider lightweight VS Code extension |
| 010 | [Competitive Differentiation](./ADR-010-competitive-differentiation.md) | Under Review — narrow to 1-2 hero features |
| 011 | [Build Sequence](./ADR-011-build-sequence.md) | **Accepted** |
| 012 | [Key Assumptions & Constraints](./ADR-012-assumptions-constraints.md) | Under Review — adjust user targets to 20-50 first |

## Implementation Scope

The 6 accepted ADRs form the build foundation:
- **002** (Open-source SDK + cloud SaaS) + **005** (same codebase, config-driven) = infrastructure approach
- **004** (LangChain first) + **006** (three integration levels, <60s to first value) = SDK priority
- **008** (API keys, tenant isolation, redaction) = security baseline
- **011** (10 weeks: cloud backend → auth+teams → beta launch) = execution timeline

The 6 under-review ADRs are deferred decisions that will be validated through beta user feedback.

## Current Reality

As of `2026-03-23`, the accepted ADRs are at different implementation stages:

- **ADR-006**: partially implemented. `agent_debugger.init()` and env-based config now exist in code.
- **ADR-008**: partially implemented. API key helpers, auth models, and redaction modules exist, but tenant enforcement and write-path integration are still pending.
- **ADR-011**: partially underway. The local debugger, benchmark seeds, and docs structure are strong; cloud-hardening work has started but is not complete.

Read [`../progress.md`](../progress.md) for the implementation snapshot that complements these decisions.
