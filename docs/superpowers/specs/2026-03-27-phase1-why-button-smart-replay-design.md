# Phase 1: "Why Did It Fail?" + Smart Replay Highlights

**Date:** 2026-03-27
**Status:** Approved
**Strategy reference:** `docs/superpowers/specs/2026-03-26-intelligence-first-strategy-design.md`

---

## Goal

Wire the existing analysis infrastructure into the frontend so a developer can click one button on a failed session and see a plain-English root cause explanation in under 30 seconds. No new backend endpoints. No LLM calls. Heuristics only, framework-agnostic.

---

## What Already Exists (no changes needed)

The codebase already has mature analysis infrastructure:

- **`GET /api/sessions/{id}/analysis`** — returns `FailureExplanation` objects with `failure_mode`, `symptom`, `likely_cause`, `confidence`, `narrative`, `candidates[]`, `supporting_event_ids`
- **`GET /api/sessions/{id}/replay?mode=highlights`** — returns highlighted events, collapsed segments, highlight indices
- **`collector/intelligence.py`** — `TraceIntelligence` composes `CausalAnalyzer` + `FailureDiagnostics` + `LiveMonitor`
- **`collector/failure_diagnostics.py`** — failure classification, symptom detection, causal analysis with confidence scoring
- **`collector/causal_analysis.py`** — BFS-based graph traversal for root cause tracing
- **`collector/replay_collapse.py`** — `identify_low_value_segments` for compressing low-value timeline sections
- **`FailureExplanationCard`** component (`App.tsx:304-331`) — button-style card showing failure mode, headline, symptom, cause, confidence
- **`diagnosis-card`** in EventDetail (`App.tsx:195-246`) — per-event diagnosis with candidates, narrative, evidence chain
- **Frontend types** `FailureExplanation`, `FailureCauseCandidate`, `Highlight`, `CollapsedSegment` — all defined in `types/index.ts`

---

## Feature 1: "Why Did It Fail?" Button

### Behavior

Failed sessions (status=ERROR, or sessions with failure events) show a prominent **"Why Did It Fail?"** button at the top of the session detail view, above the timeline.

Clicking the button calls `GET /api/sessions/{id}/analysis` and expands an inline explanation panel.

### Explanation Panel Content

Displays the first `FailureExplanation` from the analysis response. Reuses the existing `FailureExplanationCard` pattern (button-style summary cards). Shows:

- **Failure mode** badge (e.g., "tool failure", "looping behavior")
- **Symptom** (1-2 sentence description of what went wrong)
- **Likely cause** (root cause explanation)
- **Confidence score** (percentage, displayed as existing `diagnosis-badge` pattern)
- **Top candidates** (ranked list of contributing events, each clickable to scroll timeline)
- **Supporting event chain** (clickable chips that scroll to evidence events)
- **"Inspect likely cause"** button (scrolls timeline + focuses replay, existing `onSelectEvent` + `onFocusReplay` behavior)

### States

- **Idle:** Button visible, no explanation shown
- **Loading:** Spinner or skeleton, button disabled
- **Loaded:** Button stays visible (shows it was clicked), explanation panel expanded
- **Error:** Inline message "Analysis unavailable for this session" (follow existing `error-banner` CSS pattern)
- **No failures:** If analysis returns zero `failure_explanations`, show "No failure patterns detected in this session"

### API

No new endpoints. Uses existing `GET /api/sessions/{id}/analysis`.

### Component

**`WhyButton.tsx`** — manages loading/error state, fetches analysis, renders explanation panel inline. Reuses `FailureExplanationCard` pattern from `App.tsx:304-331` as the building block for the explanation card.

---

## Feature 2: Smart Replay Highlights

### Behavior

Add **"Highlights"** as an option in the replay mode selector (alongside Full, Focus, Failure).

The frontend type `ReplayMode` already includes `'highlights'` (`App.tsx:24`). The backend already supports `?mode=highlights` and returns `collapsed_segments` and `highlight_indices`.

### What Changes

- **Replay mode selector:** Add "Highlights" option (it may already be present but non-functional in the UI)
- **Timeline rendering:** In highlights mode, only show highlighted events (indices from `highlight_indices`). Show collapsed segments as `HighlightChip` components.
- **Highlight reasons:** Each highlighted event shows its reason text inline (from `generate_highlights()` in `collector/intelligence.py`)
- **Threshold control:** Three presets instead of a raw slider:
  - "Critical only" → threshold 0.7
  - "Standard" → threshold 0.35 (default, matches backend default)
  - "Show most" → threshold 0.1

### Collapsed Segment Chips

**`HighlightChip.tsx`** — renders a collapsed segment summary like "12 similar tool calls". Behavior:

- Click expands the chip in-place, replacing it with the actual events
- Expanded view shows a "Collapse" button to restore the chip
- Does not scroll or navigate — keeps the user's position in the timeline
- Follows existing `reference-chip` CSS patterns

### API

No new endpoints. Uses existing `GET /api/sessions/{id}/replay?mode=highlights&collapse_threshold={value}`.

### Frontend API Client

Add `'highlights'` to the `ReplayMode` type in `getReplay()` function params in `client.ts` (it may already be supported by the type but missing from the function signature).

---

## Layout

### Session Detail View (failed session)

```
┌──────────────────────────────────────────────────┐
│  [Session header: name, framework, status, ...]   │
│                                                    │
│  ┌─ WHY BUTTON ─────────────────────────────────┐ │
│  │  [ Why Did It Fail? ]                        │ │
│  │  ┌─ EXPANDED (on click) ──────────────────┐  │ │
│  │  │ TOOL FAILURE  87%                       │  │ │
│  │  │ Search API returned 5xx error           │  │ │
│  │  │ Likely: External API rate limit hit     │  │ │
│  │  │ [Inspect likely cause]                  │  │ │
│  │  │ Candidates: ...                         │  │ │
│  │  └─────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────┘ │
│                                                    │
│  Replay: [Full] [Focus] [Failure] [Highlights]      │
│  Threshold: [Critical] [Standard] [Show most]      │
│                                                    │
│  ┌─ TIMELINE ────────────────────────────────────┐ │
│  │  [Highlighted event] "Why: timeout detected"  │ │
│  │  [12 similar tool calls ▾]  ← HighlightChip   │ │
│  │  [Highlighted event] "Why: decision change"   │ │
│  │  [8 similar decisions ▾]      ← HighlightChip  │ │
│  │  [Highlighted event] "Why: error occurred"    │ │
│  └────────────────────────────────────────────────┘ │
│                                                    │
│  ┌─ EVENT DETAIL ────────────────────────────────┐ │
│  │  (existing EventDetail panel, unchanged)       │ │
│  └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

### Session List View

No changes in Phase 1. The session detail button is sufficient for the 30-second demo.

### Analytics View

No changes. The `DecisionTree` and `FailureClusterPanel` already display analysis data.

---

## Component Summary

| Component | Status | Purpose |
|-----------|--------|---------|
| `WhyButton.tsx` | **New** | Trigger button + explanation panel with loading/error states |
| `HighlightChip.tsx` | **New** | Collapsed segment chip with expand/collapse |
| `FailureExplanationCard` | **Existing** (reuse) | Building block for explanation card display |
| `EventDetail` | **Unchanged** | Per-event detail panel |
| `TraceTimeline` | **Modified** | Support highlights mode rendering (filter events, render chips) |

---

## Out of Scope

- LLM-enhanced explanations (Phase 4 intelligence polish)
- PydanticAI-specific error patterns (deferred)
- Session list "Explain" icon (low priority)
- Natural language debugging interface
- Counterfactual analysis

---

## Validation

The 30-second demo works end-to-end:
1. Developer runs their agent, it fails (real PydanticAI or any framework session)
2. Opens the session in Peaky Peek
3. Clicks "Why Did It Fail?"
4. Reads the explanation (failure mode, cause, confidence)
5. Clicks a candidate to jump to the relevant event in the timeline
6. Switches to Highlights mode to see the curated replay

---

## Files to Modify

| File | Change |
|------|--------|
| `frontend/src/components/WhyButton.tsx` | New — Why button + explanation panel |
| `frontend/src/components/HighlightChip.tsx` | New — collapsed segment chip |
| `frontend/src/App.tsx` | Add WhyButton above timeline, add Highlights mode to selector, add threshold presets |
| `frontend/src/api/client.ts` | Ensure `highlights` mode in `getReplay()` params |
| `frontend/src/App.css` | Styles for WhyButton, HighlightChip, highlights mode |
| `frontend/src/types/index.ts` | Add `'highlights'` to `ReplayMode` union if missing |
