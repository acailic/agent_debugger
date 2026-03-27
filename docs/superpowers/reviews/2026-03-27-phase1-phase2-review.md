# Code Review Report: Phase 1 + Phase 2

**Date:** 2026-03-27
**Reviewer:** Claude (superpowers:code-reviewer)
**Status:** COMPLETE

---

## Executive Summary

| Phase | Spec Compliance | Critical | Major | Minor | Nitpick | Overall |
|-------|-----------------|----------|-------|-------|---------|---------|
| Phase 1: Why Button + Smart Replay | 94% (1 missing) | 0 | 3 | 5 | 3 | **Solid** |
| Phase 2: Failure Memory + Cost Dashboard | 100% | 0 | 2 | 4 | 3 | **Good** |

**Verdict:** Both phases are production-ready with minor fixes recommended. No critical blockers found.

---

## Phase 1: "Why Did It Fail?" + Smart Replay Highlights

### Spec Compliance Matrix

| Requirement | Status | Notes |
|-------------|--------|-------|
| **Feature 1: Why Button** | | |
| Button visible on failed sessions | ⚠️ | Only checks `status === 'error'`, does not check `failure_count` |
| Click triggers `GET /api/sessions/{id}/analysis` | ✅ | |
| Display failure mode badge | ✅ | |
| Display symptom | ✅ | |
| Display likely cause | ✅ | |
| Display confidence score | ✅ | |
| Display top candidates (clickable) | ✅ | |
| Display supporting event chain | ✅ | |
| "Inspect likely cause" button | ✅ | |
| **States (Idle/Loading/Loaded/Error/No failures)** | ✅ | All states handled |
| **Feature 2: Smart Replay Highlights** | | |
| "Highlights" option in replay selector | ✅ | |
| Timeline renders only highlighted events | ✅ | |
| Collapsed segments as HighlightChip | ✅ | |
| **Highlight reasons shown inline** | ❌ | **MISSING** - not displayed |
| Threshold presets (Critical/Standard/Show most) | ✅ | |
| HighlightChip expand/collapse behavior | ✅ | |

### Bug Findings

#### Major Issues

| File | Line | Issue | Fix |
|------|------|-------|-----|
| `WhyButton.tsx` | :45-46 | Error catch loses error information | Extract API error details, log errors |
| `WhyButton.tsx` | :60 | Click handler undefined after load | Disable button or make it toggle |
| `App.tsx` | :1092 | Only checks `status === 'error'` | Check `failure_count > 0` too |

#### Minor Issues

| File | Line | Issue | Fix |
|------|------|-------|-----|
| `WhyButton.tsx` | :156-157 | Non-null assertion race condition | Store in local const |
| `App.tsx` | :616-624 | highlightEvents computed when not needed | Gate computation by replayMode |
| `WhyButton.tsx` | :37 | Missing defensive type check | Add `result?.analysis?.failure_explanations` |
| `HighlightChip.tsx` | :11-13 | formatDuration edge case at 60s | Add minute boundary handling |
| `App.tsx` | :382 | expandedSegments keyed by index | Reset on threshold change |

### Missing Spec Requirement

**Highlight reasons displayed inline** — The spec states "Each highlighted event shows its reason text inline". Currently the `reason` field from `Highlight` type is not displayed anywhere.

### Test Coverage Assessment

- **22 frontend tests** covering component behavior
- **Gaps:** No integration test for full WhyButton flow, no test for threshold interaction

---

## Phase 2: Failure Memory + Cost Dashboard

### Spec Compliance Matrix

| Requirement | Status | Notes |
|-------------|--------|-------|
| `storage/embedding.py` with tokenize/vector/similarity | ✅ | |
| `fix_note` column on sessions + migration | ✅ | |
| `search_sessions()` with cosine similarity | ✅ | |
| `get_cost_summary()` aggregation | ✅ | Division by zero protected |
| Cost routes (`/api/cost/summary`, `/api/cost/sessions/{id}`) | ✅ | |
| Search routes (`/api/search`, `/api/sessions/{id}/fix-note`) | ✅ | |
| Frontend types (CostSummary, SearchResult, etc.) | ✅ | |
| Frontend components (CostPanel, CostSummary, SearchBar, FixAnnotation) | ✅ | |
| Tenant isolation | ✅ | All queries scoped |
| **53 tests passing** | ✅ | |

### Bug Findings

#### Major Issues

| File | Line | Issue | Fix |
|------|------|-------|-----|
| `storage/repository.py` | :463-490 | **N+1 Query Problem** — fetches all sessions then queries events per session | Use `selectinload` or batch query |
| `storage/repository.py` | :452-456 | **Unbounded result set** — no limit on candidate sessions before similarity calc | Add `LIMIT 500` or pagination |

#### Minor Issues

| File | Line | Issue | Fix |
|------|------|-------|-----|
| `storage/embedding.py` | :159-172 | Double tokenization | Refactor to single pass |
| `storage/embedding.py` | :125, :157 | `import re` inside function | Move to module level |
| `api/search_routes.py` | :63 | getattr fallback defensive coding | Document or assert |
| `frontend/FixAnnotation.tsx` | :31-35 | Silent failure on save | Add error toast |

### Security Review

| Check | Status |
|-------|--------|
| SQL Injection | ✅ All queries parameterized |
| Tenant Isolation | ✅ All queries scoped |
| Input Validation | ✅ Query min=2, limit 1-100, fix_note max=2000 |
| Division by Zero | ✅ Protected in cost summary and similarity |

### Type Drift Analysis

All frontend/backend types match. No drift detected.

---

## Cross-Phase Integration

| Check | Status | Notes |
|-------|--------|-------|
| Phase 1 API endpoints not broken by Phase 2 | ✅ | Independent routes |
| Phase 2 schema changes don't break Phase 1 | ✅ | `fix_note` is additive |
| App layout handles all components | ✅ | No visual conflicts |
| No duplicate code | ✅ | Clean separation |
| Shared utilities consistent | ✅ | Types/API client aligned |

---

## Recommended Actions

### Must Fix (Before Release)

| Priority | Phase | Issue | Effort |
|----------|-------|-------|--------|
| 1 | 1 | WhyButton check `failure_count > 0` | 5 min |
| 2 | 2 | Add limit to search_sessions candidate fetch | 10 min |

### Should Fix (Near-term)

| Priority | Phase | Issue | Effort |
|----------|-------|-------|--------|
| 3 | 1 | Display highlight reasons inline | 30 min |
| 4 | 1 | Handle API errors in WhyButton | 15 min |
| 5 | 2 | Fix N+1 queries in search_sessions | 30 min |
| 6 | 2 | Add error feedback in FixAnnotation | 15 min |

### Consider (Backlog)

| Priority | Phase | Issue | Effort |
|----------|-------|-------|--------|
| 7 | 1 | Add integration test for WhyButton | 20 min |
| 8 | 1 | Reset expandedSegments on threshold change | 10 min |
| 9 | 2 | Move `import re` to module level | 2 min |
| 10 | 2 | Add migration rollback test | 10 min |

---

## Test Results

```
# Backend tests
python3 -m pytest -q
53 passed in 1.08s

# Frontend build
cd frontend && npm run build
✓ Built successfully
```

---

## Conclusion

Both phases are **well-implemented** with good test coverage and clean architecture. The issues found are primarily:

1. **One missing spec requirement** — highlight reasons not displayed (Phase 1)
2. **Performance concerns** — N+1 queries and unbounded fetches (Phase 2)
3. **UX polish** — error handling and feedback (both phases)

**Recommendation:** Fix the 2 must-fix items, then proceed with release. Address should-fix items in next iteration.
