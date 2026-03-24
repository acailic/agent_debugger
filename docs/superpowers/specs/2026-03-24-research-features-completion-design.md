# Research Features Completion Design

> **Spec for:** Completing Phases 3-6 of the Research Implementation Plan
>
> **Date:** 2026-03-24

---

## Overview

This design spec addresses the completion of four partially-implemented research feature phases:

| Phase | Focus | Current Status | Key Gaps |
|-------|-------|----------------|----------|
| **Phase 3** | Selective Replay | Partial | Breakpoints, segment collapsing |
| **Phase 4** | Adaptive Ranking | Partial | Retention enforcement, cross-session clustering |
| **Phase 5** | Multi-Agent Views | Partial | Benchmarked comparison, non-heuristic metrics |
| **Phase 6** | Real-Time Monitoring | Partial | Rolling summaries, loop alerts, persistence |

---

## Phase 3: Selective Replay Completion

### Current State

**Already Implemented:**
- Replay entrypoints from error, decision, refusal, checkpoint
- Focus mode with causal ancestry via `_collect_focus_scope_ids()`
- Breakpoint query parameters in API (`event_types`, `tool_names`, `confidence_below`, `safety_outcomes`)
- `matches_breakpoint()` function in `collector/replay.py`
- Frontend breakpoint inputs and auto-pause on hit

**Missing:**
- "Replay from Here" UI action
- Low-value segment collapsing
- Server-side stop at breakpoint option

### Proposed Changes

#### 3.1 "Replay from Here" UI

Add button to event detail panel that sets `mode=focus` and `focus_event_id` in single action.

**Frontend (`App.tsx`):**
```tsx
<button onClick={() => {
  setReplayMode('focus')
  setFocusEventId(selectedEventId)
}}>
  Replay from here
</button>
```

#### 3.2 Segment Collapsing Algorithm

**New Data Structure (`collector/replay.py`):**
```python
@dataclass
class CollapsedSegment:
    start_index: int
    end_index: int
    event_count: int
    summary: str  # e.g., "12 routine tool calls"
    event_types: list[str]
    total_duration_ms: float | None = None
```

**Algorithm:**
```python
def identify_low_value_segments(
    events: list[TraceEvent],
    threshold: float = 0.35,
    min_segment_length: int = 3,
    context_window: int = 1,
) -> list[CollapsedSegment]:
    """Identify contiguous sequences of low-importance events."""
    # 1. Mark events as high/low value based on importance threshold
    # 2. Protect events near high-value events (context window)
    # 3. Find contiguous runs of low-value events >= min_segment_length
    # 4. Create CollapsedSegment objects with summaries
```

#### 3.3 API Changes

**New Mode (`api/replay_routes.py`):**
```python
mode: str = Query(default="full", pattern="^(full|focus|failure|highlights)$")
stop_at_breakpoint: bool = Query(default=False)
```

**Schema Changes (`api/schemas.py`):**
```python
class ReplayResponse(BaseModel):
    # ... existing fields ...
    collapsed_segments: list[CollapsedSegment] = []
    highlight_indices: list[int] = []
    stopped_at_breakpoint: bool = False
    stopped_at_index: int | None = None
```

### Files Changed

| File | Action |
|------|--------|
| `collector/replay.py` | Add `CollapsedSegment`, `identify_low_value_segments()`, `build_condensed_replay()` |
| `api/replay_routes.py` | Add `highlights` mode, `stop_at_breakpoint` param |
| `api/schemas.py` | Add `CollapsedSegment` schema |
| `frontend/src/App.tsx` | Add "Replay from here", highlights mode |
| `frontend/src/types/index.ts` | Add `CollapsedSegment` type |

---

## Phase 4: Adaptive Ranking and Retention Completion

### Current State

**Already Implemented:**
- Event-level importance scoring via `ImportanceScorer`
- Session-level replay value formula
- Retention tier computation (but not persistence)
- Within-session failure clustering

**Missing:**
- Retention tier persistence and enforcement
- Cross-session failure clustering
- Tier-aware data lifecycle

### Proposed Changes

#### 4.1 Retention Tier Persistence

**Database Changes (`storage/models.py`):**
```python
# Add to SessionModel
retention_tier: Mapped[str] = mapped_column(String(16), default="downsampled", index=True)
failure_fingerprint_primary: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
cluster_representative: Mapped[bool] = mapped_column(default=False, index=True)
```

**New Table:**
```python
class FailureClusterModel(Base):
    __tablename__ = "failure_clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="local", index=True)
    fingerprint: Mapped[str] = mapped_column(String(255), index=True)
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]
    session_count: Mapped[int] = mapped_column(default=1)
    event_count: Mapped[int] = mapped_column(default=0)
    representative_session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"))
    representative_event_id: Mapped[str] = mapped_column(String(36))
    sample_failure_mode: Mapped[str] = mapped_column(String(64))
    sample_symptom: Mapped[str] = mapped_column(String(512))
    avg_severity: Mapped[float] = mapped_column(Float, default=0.0)
```

#### 4.2 Retention Enforcement

**New Module (`storage/retention_enforcement.py`):**

| Tier | Session Metadata | Events | Checkpoints |
|------|------------------|--------|-------------|
| `full` | All | All events, full data | All |
| `summarized` | All | Keep event, strip `data`, `messages`, `result` | Keep only importance >= 0.8 |
| `downsampled` | All | Delete all | Delete all |

```python
class RetentionEnforcer:
    async def apply_retention_policy(
        self,
        sessions: list[Session],
        tier_config: RetentionConfig,
    ) -> RetentionResult:
        """Apply retention policy based on tier."""
```

#### 4.3 Cross-Session Clustering

**New Module (`collector/cross_session_clustering.py`):**
```python
class CrossSessionClusterer:
    async def cluster_failures(
        self,
        sessions: list[Session],
        events_by_session: dict[str, list[TraceEvent]],
        time_window_days: int = 7,
    ) -> list[CrossSessionCluster]:
        """
        Algorithm:
        1. Extract all failure events (severity >= 0.78)
        2. Group by fingerprint
        3. For each group:
           - Compute cluster score: session_count * avg_severity
           - Select representative: highest composite in most recent session
        4. Mark representative sessions with cluster_representative=True
        """
```

#### 4.4 API Changes

**New Endpoints:**
```
GET /api/clusters?agent_name={agent_name}&days={days}
GET /api/clusters/{cluster_id}/sessions
POST /api/admin/retention/enforce
```

### Files Changed

| File | Action |
|------|--------|
| `storage/models.py` | Add columns, `FailureClusterModel` table |
| `storage/repository.py` | Add cluster queries |
| `storage/retention_enforcement.py` | New module |
| `collector/cross_session_clustering.py` | New module |
| `api/session_routes.py` | Add cluster endpoints |
| `frontend/src/components/FailureClusterPanel.tsx` | New component |

---

## Phase 5: Multi-Agent and Prompt-Policy Views Completion

### Current State

**Already Implemented:**
- Conversation panel with agent_turn/prompt_policy visibility
- Two-session comparison view
- Heuristic metrics (stance shift count, keyword escalation, evidence count)

**Missing:**
- Benchmarked comparison semantics
- Non-heuristic stance-shift metrics
- Non-heuristic escalation metrics
- Stronger turn sequence summaries

### Proposed Changes

#### 5.1 Benchmarked Comparison

**Extend `AgentBaseline` (`collector/baseline.py`):**
```python
multi_agent_metrics:
    avg_policy_shifts_per_session: float
    avg_turns_per_session: int
    avg_speaker_count: float
    escalation_pattern_rate: float
    evidence_grounding_rate: float
    coordination_efficiency: float
```

**New Response Schema:**
```python
class BenchmarkedComparisonResponse(BaseModel):
    primary_session_id: str
    secondary_session_id: str
    baseline: AgentBaseline
    normalized_metrics: dict[str, float]  # Z-scores
    policy_comparison: PolicyComparisonResult
    turn_comparison: TurnSequenceComparison
```

#### 5.2 Non-Heuristic Stance-Shift Metrics

**New Module (`collector/policy_analysis.py`):**
```python
@dataclass
class PolicyShift:
    event_id: str
    previous_template: str | None
    new_template: str
    parameter_changes: dict[str, ParameterChange]
    shift_magnitude: float  # 0.0-1.0
    triggering_turn_id: str | None

def analyze_policy_sequence(
    policies: list[PromptPolicyEvent],
    turns: list[AgentTurnEvent],
) -> list[PolicyShift]:
    """Analyze policy changes with semantic understanding."""
    # 1. Detect template changes
    # 2. Diff parameters for same-template policies
    # 3. Compute magnitude based on parameter importance
    # 4. Link to nearest upstream turn
```

#### 5.3 Non-Heuristic Escalation Metrics

**New Module (`collector/escalation_detection.py`):**
```python
@dataclass
class EscalationSignal:
    event_id: str
    turn_index: int
    signal_type: Literal[
        "explicit_keyword",       # Lower weight
        "confidence_degradation", # Decision confidence dropping
        "tool_stake_increase",    # Tools becoming higher-stakes
        "decision_chain_depth",   # Deep upstream chains
        "safety_pressure",        # Safety/refusal events increasing
        "handoff_pattern",        # Speaker changes with goal transfer
    ]
    magnitude: float
    evidence_event_ids: list[str]

# Weighted escalation score
WEIGHTS = {
    "explicit_keyword": 0.15,
    "confidence_degradation": 0.25,
    "tool_stake_increase": 0.20,
    "decision_chain_depth": 0.15,
    "safety_pressure": 0.15,
    "handoff_pattern": 0.10,
}
```

#### 5.4 Turn Sequence Summarization

**New Module (`collector/turn_summarization.py`):**
```python
@dataclass
class TurnSequenceSummary:
    phases: list[PhaseSummary]
    coordination_patterns: list[CoordinationPattern]
    narrative_arc: str
    key_transitions: list[Transition]

@dataclass
class PhaseSummary:
    phase_type: Literal["exploration", "planning", "execution", "deliberation", "escalation", "resolution"]
    start_turn: int
    end_turn: int
    speakers: list[str]
    dominant_goals: list[str]
```

### Files Changed

| File | Action |
|------|--------|
| `collector/baseline.py` | Add multi-agent metrics |
| `collector/policy_analysis.py` | New module |
| `collector/escalation_detection.py` | New module |
| `collector/turn_summarization.py` | New module |
| `api/schemas.py` | Add comparison schemas |
| `api/comparison_routes.py` | New endpoint |
| `frontend/src/components/SessionComparisonPanel.tsx` | Use API metrics |
| `frontend/src/components/PolicyDiffView.tsx` | New component |

---

## Phase 6: Real-Time Monitoring and Alerts Completion

### Current State

**Already Implemented:**
- Behavior alerts (in-memory)
- SSE subscription path
- Live session pulse panel
- Basic anomaly detection (3-consecutive tool loops)

**Missing:**
- Stronger rolling summaries
- Explicit loop/oscillation alert timelines
- Anomaly history persistence
- Checkpoint delta display

### Proposed Changes

#### 6.1 Rolling Summary Algorithm

**New Data Structure (`collector/live_monitor.py`):**
```python
@dataclass
class RollingWindow:
    window_start: datetime
    window_end: datetime
    event_count: int
    tool_calls: int
    llm_calls: int
    decisions: int
    errors: int
    refusals: int
    total_tokens: int
    total_cost_usd: float
    unique_tools: set[str]
    unique_agents: set[str]
    avg_confidence: float
    state_progression: list[str]

@dataclass
class RollingSummary:
    text: str  # Human-readable synthesized summary
    metrics: dict[str, Any]  # Structured metrics for UI
    window_type: str  # "time" or "event_count"
    window_size: int  # seconds or event count
    computed_at: datetime
```

**Configuration:**
- Default: 60-second rolling window
- Alternative: Last 50 events

#### 6.2 Oscillation Detection

**New Algorithm:**
```python
def detect_oscillation(events: list[TraceEvent], window: int = 10) -> OscillationAlert | None:
    """
    Detect A->B->A->B patterns in tool calls or decisions.

    Algorithm:
    1. Extract sequence of (event_type, key_field) tuples
    2. For each subsequence length 2-4:
       - Check if sequence repeats at least twice
       - Compute oscillation score: repeat_count / window_size
    3. Return highest-scoring oscillation with severity
    """
```

**New Detection Types:**
- **State Regression**: Agent returns to previous state after progress
- **Configurable Loop Detection**: Make consecutive-count configurable

#### 6.3 Anomaly History Persistence

**New Table (`storage/models.py`):**
```python
class AnomalyAlertModel(Base):
    __tablename__ = "anomaly_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="local", index=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), index=True)
    alert_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[float] = mapped_column(Float)  # 0.0-1.0 continuous
    signal: Mapped[str] = mapped_column(Text)
    event_ids: Mapped[list] = mapped_column(JSON)
    detection_source: Mapped[str] = mapped_column(String(32))
    detection_config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime]
```

**New Service (`collector/alert_persister.py`):**
```python
class AlertPersister:
    async def persist_alerts(
        self,
        session_id: str,
        alerts: list[DerivedAlert],
    ) -> list[AnomalyAlert]:
        """Persist derived alerts to database."""
```

#### 6.4 Checkpoint Delta Display

**New Data Structure:**
```python
@dataclass
class CheckpointDelta:
    checkpoint_id: str
    event_id: str
    sequence: int
    time_since_previous: float  # seconds
    events_since_previous: int
    importance_delta: float
    restore_value: float
    state_keys_changed: list[str]
```

**API Enhancement:**
```
GET /api/sessions/{session_id}/checkpoints/deltas
```

### Files Changed

| File | Action |
|------|--------|
| `storage/models.py` | Add `AnomalyAlertModel` table |
| `storage/repository.py` | Add alert queries |
| `collector/live_monitor.py` | Add `RollingWindow`, oscillation detection |
| `collector/alert_persister.py` | New module |
| `api/trace_routes.py` | Add alert endpoints |
| `frontend/src/components/LiveSummaryPanel.tsx` | Display rolling summary, checkpoint deltas |
| `frontend/src/components/AnomalyAlertTimeline.tsx` | New component |

---

## Implementation Order

### Sprint 1: Foundation (Database + Core Algorithms)

1. **Database Migrations** (~2h)
   - Add `retention_tier`, `failure_fingerprint_primary`, `cluster_representative` to `sessions`
   - Create `failure_clusters` table
   - Create `anomaly_alerts` table

2. **Phase 4.2: Retention Enforcement** (~4h)
   - Create `RetentionEnforcer` module
   - Implement tier-aware data lifecycle

3. **Phase 3.2: Segment Collapsing** (~4h)
   - Implement `identify_low_value_segments()`
   - Implement `build_condensed_replay()`

### Sprint 2: Intelligence Features

4. **Phase 4.3: Cross-Session Clustering** (~4h)
   - Create `CrossSessionClusterer`
   - Integrate with session finalization

5. **Phase 5.2-5.3: Non-Heuristic Metrics** (~6h)
   - Create `policy_analysis.py`
   - Create `escalation_detection.py`

6. **Phase 6.1-6.2: Rolling Summaries + Oscillation** (~4h)
   - Implement `RollingWindow` aggregation
   - Implement oscillation detection

### Sprint 3: API + Frontend

7. **Phase 3.3: Replay API** (~2h)
   - Add `highlights` mode
   - Add `stop_at_breakpoint`

8. **Phase 5.1: Benchmarked Comparison** (~3h)
   - Create comparison endpoint
   - Extend baseline metrics

9. **Phase 6.3: Alert Persistence** (~3h)
   - Create `AlertPersister`
   - Add alert endpoints

10. **Frontend Updates** (~8h)
    - "Replay from here" button
    - Highlights mode navigation
    - Failure cluster panel
    - Policy diff view
    - Rolling summary display
    - Anomaly timeline

### Sprint 4: Testing + Documentation

11. **Unit Tests** (~4h)
12. **Integration Tests** (~4h)
13. **API Documentation** (~2h)

**Total Estimated Time:** 50-60 hours

---

## Exit Criteria Verification

| Phase | Criterion | Status After Implementation |
|-------|-----------|----------------------------|
| **3** | User can replay only relevant branch | ✅ "Replay from here" + focus mode |
| **3** | Replay stops on configured breakpoints | ✅ `stop_at_breakpoint` option |
| **4** | Sessions sortable by replay value | ✅ Already works |
| **4** | Retention distinguishes routine from high-value | ✅ Tier enforcement + data lifecycle |
| **5** | Multi-agent traces understandable without raw payloads | ✅ Turn summaries + phase detection |
| **5** | Prompt-policy changes comparable across runs | ✅ Benchmarked comparison + policy diff |
| **6** | Active sessions monitorable without full stream | ✅ Rolling summaries + live metrics |
| **6** | Unstable behavior surfaced proactively | ✅ Oscillation detection + alert persistence |

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Database migration complexity | Test on copy first, use Alembic downgrade |
| Performance impact of clustering | Background jobs, batch processing |
| Frontend scope creep | Prioritize core workflows, defer polish |
| API contract changes | Version new endpoints, maintain backward compat |
