# ADR-007: Replay Fidelity Strategy

**Status:** Under Review
**Date:** 2026-03-23

## Open Challenge

Positioning replay as "not deterministic" may frustrate users who expect time-travel debugging to mean exact reproduction. The honesty is technically correct but may hurt adoption.

**Action:** Test with users. Frame as "replay + what-if" rather than "structural replay." The feature should feel powerful, not limited. If users want cached-response deterministic replay for specific sessions, consider it as an opt-in mode (record and replay exact LLM responses).

---

## Original Decision (Deferred)

Three replay modes:
1. **Event Replay** (read-only): Replay recorded event stream exactly
2. **Focused Replay** (filtered read-only): Filtered to specific branch/error path
3. **Re-execution Replay** (from checkpoint): Restore state and re-run, showing divergence

Key principle: structural replay over deterministic, because LLM non-determinism makes exact replay impossible without caching all responses.

Possible revision: add a fourth mode — **Cached Replay** — that records and replays exact LLM responses for sessions the user marks as important. Higher storage cost but gives deterministic feel when desired.
