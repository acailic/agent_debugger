# Core Analysis Features: Design Specification

**Date**: 2026-03-24
**Status**: Ready for Implementation
**Scope**: Features 1, 3, 4 from TOP_5_NO_BRAINER_FEATURES_IMPLEMENTATION.md

---

## Overview

This spec covers three high-impact features that transform the debugger from "useful" to "must-have":

1. **"Why Did It Fail?" Button** - One-click failure explanation
2. **Smart Replay Highlights** - AI-curated key moments
3. **Behavior Change Alerts** - Per-agent drift detection

All features are **local-first** with optional LLM enhancement.

---

## Feature 1: "Why Did It Fail?" Button

### Problem
Users have 500+ events and no idea which one caused the failure. Current UI requires clicking on a failure event to see the explanation - too many steps.

### Solution
Add a prominent "Why Did It Fail?" button that:
- Appears when a session has failures
- One click shows the top failure explanation
- Provides instant root cause with confidence score
- Links directly to the culprit event

### Implementation

#### Backend (Already done)
- `CausalAnalyzer.rank_failure_candidates()` - BFS-based causal ranking
- `FailureDiagnostics.build_failure_explanations()` - Narrative generation
- `/api/sessions/{session_id}/analysis` returns `failure_explanations`

#### Frontend Changes

1. **Session Card Enhancement**
   - Add "Why?" button on sessions with failures
   - Button shows failure count badge
   - Click triggers explanation modal

2. **FailureExplanationModal Component** (new)
   ```
   - Shows top failure explanation
   - Displays: symptom, likely cause, confidence
   - "Inspect cause" button jumps to culprit event
   - "See all failures" shows full list
   ```

3. **Visual Prominence**
   - Failure explanations get a highlighted card style
   - Confidence score shown as progress bar
   - Causal chain shown as clickable breadcrumbs

### Files to Change
- `frontend/src/components/FailureExplanationModal.tsx` (new)
- `frontend/src/App.tsx` - Add modal trigger, session card button
- `frontend/src/App.css` - Modal and button styles

---

## Feature 3: Smart Replay Highlights

### Problem
Long sessions (10+ minutes) are tedious to review. Most events are routine. Important moments are buried.

### Solution
Add a "Highlights" replay mode that:
- Auto-curates key moments from the session
- Shows only: decisions, errors, refusals, state changes, anomalies
- Provides navigation to jump between highlights
- Collapses routine segments

### Implementation

#### Backend Changes

1. **Highlight Generation** (extend `collector/intelligence.py`)
   ```python
   def generate_highlights(events, rankings) -> list[Highlight]:
       # Score events for highlight-worthiness
       # Group into segments
       # Return curated list with timestamps
   ```

2. **Highlight Schema**
   ```python
   @dataclass
   class Highlight:
       event_id: str
       highlight_type: str  # decision, error, refusal, anomaly, state_change
       importance: float
       reason: str  # "Low confidence decision", "Tool error", etc.
       segment_start: int  # Index in event list
       segment_end: int
   ```

3. **API Extension**
   - Add `highlights` field to `TraceAnalysis` response
   - Each highlight includes event, type, reason

#### Frontend Changes

1. **Highlights Mode Toggle**
   - Add "highlights" to replay mode switcher (full/focus/failure/highlights)

2. **Highlight Timeline**
   - Show markers on timeline for highlight positions
   - Click marker jumps to that event

3. **Highlight Navigation**
   - "Next highlight" / "Prev highlight" buttons
   - Shows current position (e.g., "3 of 7 highlights")

4. **Highlight Card**
   - When on a highlight, show reason card
   - "Why is this highlighted? Low confidence decision (0.32)"

### Files to Change
- `collector/intelligence.py` - Add `generate_highlights()`
- `api/schemas.py` - Add `HighlightSchema`
- `frontend/src/types/index.ts` - Add `Highlight` type
- `frontend/src/App.tsx` - Highlights mode, navigation
- `frontend/src/App.css` - Highlight markers, cards

---

## Feature 4: Behavior Change Alerts

### Problem
"My agent worked yesterday. Today it's failing. I don't know what changed."

No tool tracks behavioral drift over time. Issues caught after user complaints.

### Solution
Add per-agent baseline tracking and drift detection:
- Compute baseline from last 7 days of sessions (per agent_name)
- Compare recent sessions (last 24h) to baseline
- Alert on significant changes with root cause

### Implementation

#### Backend Changes

1. **Behavior Baseline** (new file `collector/baseline.py`)
   ```python
   @dataclass
   class AgentBaseline:
       agent_name: str
       session_count: int
       time_window_days: int

       # Decision patterns
       avg_decision_confidence: float
       low_confidence_rate: float

       # Performance
       avg_tool_duration_ms: float
       error_rate: float

       # Cost
       avg_cost_per_session: float
       avg_tokens_per_session: int

       # Behavior
       tool_loop_rate: float
       refusal_rate: float

   def compute_baseline(agent_name: str, sessions: list[Session]) -> AgentBaseline
   def detect_drift(baseline: AgentBaseline, recent: AgentBaseline) -> list[DriftAlert]
   ```

2. **Drift Detection**
   ```python
   @dataclass
   class DriftAlert:
       metric: str  # "decision_confidence", "error_rate", etc.
       baseline_value: float
       current_value: float
       change_percent: float
       severity: str  # "warning", "critical"
       likely_cause: str | None  # "Temperature changed from 0.3 to 0.7"
   ```

3. **API Endpoints**
   - `GET /api/agents/{agent_name}/baseline` - Get current baseline
   - `GET /api/agents/{agent_name}/drift` - Get drift alerts
   - Add `baseline` and `drift_alerts` to session analysis when available

4. **Storage**
   - Store computed baselines in SQLite (cache, recompute on demand)
   - Table: `agent_baselines` with JSON metrics blob

#### Frontend Changes

1. **Agent Baseline Panel** (new component)
   - Shows current agent's baseline metrics
   - Displays "X sessions over 7 days"
   - Shows key metrics with sparklines

2. **Drift Alerts Section**
   - Appears in analysis ribbon when drift detected
   - Shows: metric, change, severity, likely cause
   - Color-coded: yellow (warning), red (critical)

3. **Session List Enhancement**
   - Show drift indicator on sessions with changes
   - Filter by "has drift alerts"

### Files to Change
- `collector/baseline.py` (new) - Baseline computation, drift detection
- `api/schemas.py` - Add `AgentBaselineSchema`, `DriftAlertSchema`
- `api/trace_routes.py` - Add baseline/drift endpoints
- `storage/repository.py` - Add baseline queries
- `storage/migrations/` - Add agent_baselines table
- `frontend/src/types/index.ts` - Add types
- `frontend/src/components/DriftAlertsPanel.tsx` (new)
- `frontend/src/App.tsx` - Integrate drift panel

---

## Implementation Order

**Phase 1: Feature 1 (Why Button)**
- Frontend only, backend ready
- Quick win, high visibility
- ~2-3 hours

**Phase 2: Feature 3 (Highlights)**
- Backend: add highlight generation
- Frontend: highlights mode + navigation
- ~4-5 hours

**Phase 3: Feature 4 (Drift Alerts)**
- Backend: baseline + drift detection
- Storage: migrations
- Frontend: drift panel
- ~5-6 hours

---

## Success Criteria

| Feature | Metric |
|---------|--------|
| Why Button | User can explain any failure in < 10 seconds from session list |
| Highlights | 10-minute session reviewable in < 2 minutes |
| Drift Alerts | 70% of behavioral issues detected before user reports |

---

## Dependencies

- All features: No external dependencies (local-first)
- Optional LLM: For richer explanations (user-provided API key)
