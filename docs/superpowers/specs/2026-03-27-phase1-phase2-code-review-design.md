# Code Review Design: Phase 1 + Phase 2

**Date:** 2026-03-27
**Status:** Approved
**Review Target:** Phase 1 (Why Button + Smart Replay) + Phase 2 (Failure Memory + Cost Dashboard)

---

## Goals

1. **Quality gate** — Verify implementations meet their specs before considering phases "done"
2. **Bug hunting** — Find potential issues, edge cases, and regressions

---

## Methodology

For each phase:

1. **Read the spec** — Understand what was promised
2. **Read the implementation** — All changed files for that phase
3. **Run tests** — Verify existing tests pass, assess coverage gaps
4. **Check spec compliance** — Verify each spec requirement is implemented
5. **Hunt bugs** — Look for edge cases, error handling gaps, type safety issues
6. **Document findings** — Categorized as Critical / Major / Minor / Nitpick

---

## Phase 1: "Why Did It Fail?" + Smart Replay Highlights

**Spec reference:** `docs/superpowers/specs/2026-03-27-phase1-why-button-smart-replay-design.md`

### Files to Review

| File | Type | Purpose |
|------|------|---------|
| `frontend/src/components/WhyButton.tsx` | New | Why button + explanation panel |
| `frontend/src/components/HighlightChip.tsx` | New | Collapsed segment chip |
| `frontend/src/App.tsx` | Modified | Integration point |
| `frontend/src/App.css` | Modified | Styles |
| `frontend/src/api/client.ts` | Modified | API client |
| `frontend/src/types/index.ts` | Modified | Types |
| `frontend/src/__tests__/WhyButton.test.tsx` | New | Tests |
| `frontend/src/__tests__/HighlightChip.test.tsx` | New | Tests |

### Compliance Checks

- [ ] WhyButton shows on failed sessions (status=ERROR or failure events)
- [ ] Click triggers `GET /api/sessions/{id}/analysis`
- [ ] Explanation panel shows: failure mode badge, symptom, likely cause, confidence, candidates, supporting events
- [ ] "Inspect likely cause" scrolls timeline + focuses replay
- [ ] States handled: Idle, Loading, Loaded, Error, No failures
- [ ] "Highlights" mode in replay selector
- [ ] HighlightChip renders collapsed segments with expand/collapse
- [ ] Threshold presets: Critical (0.7), Standard (0.35), Show most (0.1)
- [ ] No new backend endpoints (uses existing)

### Bug Hunting Focus

- Error states — what if API returns 500, malformed JSON, timeout?
- Empty states — session with no events, no failures, no highlights
- Type safety — are all optional fields handled?
- Memory — any event listener or subscription leaks?

---

## Phase 2: Failure Memory + Cost Dashboard

**Spec reference:** `docs/superpowers/plans/2026-03-26-phase2-failure-memory-cost-dashboard.md`

### Files to Review

| File | Type | Purpose |
|------|------|---------|
| `storage/embedding.py` | New | Bag-of-words similarity |
| `api/cost_routes.py` | New | Cost aggregation API |
| `api/search_routes.py` | New | Failure memory search API |
| `storage/versions/004_add_session_fix_note.py` | New | DB migration |
| `storage/engine.py` | Modified | Migration registration |
| `storage/repository.py` | Modified | New query methods |
| `api/schemas.py` | Modified | New response types |
| `frontend/src/components/CostPanel.tsx` | New | Per-session cost |
| `frontend/src/components/CostSummary.tsx` | New | Aggregate dashboard |
| `frontend/src/components/SearchBar.tsx` | New | Failure memory search |
| `frontend/src/components/FixAnnotation.tsx` | New | Fix note editor |
| `frontend/src/App.tsx` | Modified | Integration |
| `frontend/src/api/client.ts` | Modified | New API calls |
| `frontend/src/types/index.ts` | Modified | New types |
| `tests/test_cost_api.py` | New | Tests |
| `tests/test_search_api.py` | New | Tests |
| `tests/test_embedding.py` | New | Tests |
| `tests/test_phase2_integration.py` | New | Integration tests |

### Compliance Checks

- [ ] `text_to_vector()` produces consistent embeddings
- [ ] `cosine_similarity()` handles edge cases (empty, orthogonal)
- [ ] `GET /api/cost/summary` returns aggregate costs (day/week/month)
- [ ] `GET /api/cost/session/{id}` returns per-session breakdown
- [ ] `GET /api/search/sessions` returns similar sessions via cosine similarity
- [ ] `PATCH /api/sessions/{id}/fix_note` persists fix annotations
- [ ] Database migration runs cleanly
- [ ] Frontend components integrate into App layout
- [ ] Types match between frontend and backend schemas

### Bug Hunting Focus

- **SQL injection** — are queries parameterized?
- **Division by zero** — in cost aggregation, similarity calculation
- **Empty embeddings** — sessions with no events
- **Large result sets** — pagination for search results?
- **Migration rollback** — what if migration fails mid-way?
- **Concurrent writes** — race conditions on fix_note updates?
- **Type drift** — do frontend types match backend schemas exactly?

---

## Cross-Phase Integration

### Integration Checks

- [ ] Phase 1's analysis endpoint doesn't break Phase 2's new routes
- [ ] Phase 2's schema changes don't break Phase 1 components
- [ ] App layout handles all new components without visual conflicts
- [ ] No duplicate code between phases (DRY check)
- [ ] Shared utilities (types, API client) remain consistent

### Test Coverage Assessment

- Run `python3 -m pytest -q` — all backend tests pass
- Run `cd frontend && npm run build` — no TypeScript errors
- Assess: Are edge cases from bug hunting covered by tests?

---

## Deliverables

1. **Review Report** (`docs/superpowers/reviews/2026-03-27-phase1-phase2-review.md`)
   - Spec compliance matrix for each phase
   - Bug findings table (severity, file, line, description, recommendation)
   - Test coverage assessment

2. **Actionable Next Steps**
   - Critical bugs → fix immediately
   - Major issues → create issues/plan to address
   - Minor/Nitpicks → optional cleanup

---

## Severity Definitions

| Severity | Definition | Action |
|----------|------------|--------|
| **Critical** | Blocks core functionality, data loss, security vulnerability | Fix immediately |
| **Major** | Breaks feature in common scenario, poor UX | Fix before release |
| **Minor** | Edge case issue, inconsistent behavior | Fix when convenient |
| **Nitpick** | Style, naming, minor cleanup | Optional |
