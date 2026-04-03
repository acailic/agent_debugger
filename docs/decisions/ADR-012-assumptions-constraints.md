# ADR-012: Key Assumptions & Constraints

**Status:** Accepted
**Date:** 2026-03-23

## Open Challenge

100-200 paying users within 6 months is optimistic without validation. More realistic first target: 20-50 paying users. Plan infrastructure and effort for that scale first, then grow.

**Action:** Set milestones:
- Month 1-2: 10 beta users (free)
- Month 3: 20-30 active users, 5-10 paying
- Month 6: 50+ active users, 20-50 paying
- Revenue target adjusted: $1k-5k MRR at month 6, $5k-20k MRR at month 12

## Resolution

Revised milestones adopted: 20-50 paying users at month 6 with $1k-5k MRR. More realistic than original 100-200 paying users. All other approved assumptions (volume, technical, constraints) remain valid. Infrastructure and effort planning should target the revised scale first, then grow.

---

## Approved Assumptions (Still Valid)

### Volume
- Events per session: 50-500 typical, 10k max
- Sessions per developer per day: 5-20
- Event size: 1-10 KB typical, 100KB max

### Technical
- SQLite sufficient for local mode
- Python is primary language for agent development
- SSE sufficient for live streaming v1

### Constraints
- 1-2 developers for initial build
- Bootstrapped / early revenue
- 10-week build to first beta users
- Must work with Python 3.10+, LangChain 0.2+

### User & Revenue Targets (Revised)
- Month 1-2: 10 beta users (free)
- Month 3: 20-30 active users, 5-10 paying
- Month 6: 50+ active users, 20-50 paying
- Revenue target: $1k-5k MRR at month 6, $5k-20k MRR at month 12
