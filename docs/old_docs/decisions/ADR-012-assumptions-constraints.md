# ADR-012: Key Assumptions & Constraints

**Status:** Under Review
**Date:** 2026-03-23

## Open Challenge

100-200 paying users within 6 months is optimistic without validation. More realistic first target: 20-50 paying users. Plan infrastructure and effort for that scale first, then grow.

**Action:** Set milestones:
- Month 1-2: 10 beta users (free)
- Month 3: 20-30 active users, 5-10 paying
- Month 6: 50+ active users, 20-50 paying
- Revenue target adjusted: $1k-5k MRR at month 6, $5k-20k MRR at month 12

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
