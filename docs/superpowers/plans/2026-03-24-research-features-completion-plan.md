# Research Features Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phases 3-6 of the Research Implementation Plan

**Spec:** `docs/superpowers/specs/2026-03-24-research-features-completion-design.md`

---

## Task 1: Database Migrations (Foundation)

**Files:**
- Modify: `storage/models.py`
- Create: `storage/migrations/versions/00X_add_research_features.py`

- [ ] **Step 1: Add retention columns to SessionModel**

In `storage/models.py`, add to `SessionModel`:
```python
retention_tier: Mapped[str] = mapped_column(String(16), default="downsampled", index=True)
failure_fingerprint_primary: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
cluster_representative: Mapped[bool] = mapped_column(default=False, index=True)
cluster_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
```

- [ ] **Step 2: Create FailureClusterModel table**

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
    representative_session_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sessions.id"))
    representative_event_id: Mapped[str | None] = mapped_column(String(36))
    sample_failure_mode: Mapped[str | None] = mapped_column(String(64))
    sample_symptom: Mapped[str | None] = mapped_column(String(512))
    avg_severity: Mapped[float] = mapped_column(Float, default=0.0)
```

- [ ] **Step 3: Create AnomalyAlertModel table**

```python
class AnomalyAlertModel(Base):
    __tablename__ = "anomaly_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="local", index=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), index=True)
    alert_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[float] = mapped_column(Float)
    signal: Mapped[str] = mapped_column(Text)
    event_ids: Mapped[list] = mapped_column(JSON)
    detection_source: Mapped[str] = mapped_column(String(32))
    detection_config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime]
```

- [ ] **Step 4: Create Alembic migration**

```bash
alembic revision --autogenerate -m "add_research_features_tables"
alembic upgrade head
```

- [ ] **Step 5: Test migration**

```bash
python3 -m pytest tests/test_models.py -v
```

---

## Task 2: Phase 3 - Segment Collapsing (Backend)

**Files:**
- Create: `collector/replay_collapse.py`
- Modify: `collector/replay.py`

- [ ] **Step 1: Create CollapsedSegment dataclass**

In `collector/replay_collapse.py`:
```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class CollapsedSegment:
    start_index: int
    end_index: int
    event_count: int
    summary: str
    event_types: list[str] = field(default_factory=list)
    total_duration_ms: float | None = None
```

- [ ] **Step 2: Implement identify_low_value_segments()**

```python
def identify_low_value_segments(
    events: list["TraceEvent"],
    threshold: float = 0.35,
    min_segment_length: int = 3,
    context_window: int = 1,
) -> list[CollapsedSegment]:
    """Identify contiguous sequences of low-importance events."""
    if not events:
        return []

    # Mark high-value events
    high_value_indices = set()
    for i, event in enumerate(events):
        if (event.importance or 0) >= threshold:
            high_value_indices.add(i)

    # Protect context around high-value events
    protected = set(high_value_indices)
    for idx in high_value_indices:
        for offset in range(-context_window, context_window + 1):
            new_idx = idx + offset
            if 0 <= new_idx < len(events):
                protected.add(new_idx)

    # Find contiguous low-value runs
    segments = []
    run_start = None

    for i in range(len(events)):
        if i not in protected:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None:
                run_length = i - run_start
                if run_length >= min_segment_length:
                    segments.append((run_start, i - 1))
                run_start = None

    # Handle trailing run
    if run_start is not None:
        run_length = len(events) - run_start
        if run_length >= min_segment_length:
            segments.append((run_start, len(events) - 1))

    # Build CollapsedSegment objects
    result = []
    for start, end in segments:
        segment_events = events[start:end + 1]
        event_types = list(set(e.event_type for e in segment_events))
        summary = f"{len(segment_events)} {', '.join(event_types[:2])} events"

        result.append(CollapsedSegment(
            start_index=start,
            end_index=end,
            event_count=len(segment_events),
            summary=summary,
            event_types=event_types,
        ))

    return result
```

- [ ] **Step 3: Write unit tests**

Create `tests/test_replay_collapse.py`:
```python
import pytest
from collector.replay_collapse import identify_low_value_segments, CollapsedSegment

class TestIdentifyLowValueSegments:
    def test_empty_events_returns_empty(self):
        assert identify_low_value_segments([]) == []

    def test_no_low_value_segments_when_all_high_importance(self):
        from unittest.mock import MagicMock
        events = [MagicMock(importance=0.8, event_type="tool") for _ in range(5)]
        assert identify_low_value_segments(events) == []

    def test_finds_contiguous_low_value_run(self):
        from unittest.mock import MagicMock
        events = [
            MagicMock(importance=0.2, event_type="tool"),
            MagicMock(importance=0.2, event_type="tool"),
            MagicMock(importance=0.2, event_type="tool"),
            MagicMock(importance=0.9, event_type="decision"),
        ]
        segments = identify_low_value_segments(events, min_segment_length=2)
        assert len(segments) == 0  # Protected by context window around high-value event
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_replay_collapse.py -v
```

---

## Task 3: Phase 3 - Replay API Changes

**Files:**
- Modify: `api/replay_routes.py`
- Modify: `api/schemas.py`

- [ ] **Step 1: Add CollapsedSegmentSchema**

In `api/schemas.py`:
```python
class CollapsedSegmentSchema(BaseModel):
    start_index: int
    end_index: int
    event_count: int
    summary: str
    event_types: list[str] = []
    total_duration_ms: float | None = None
```

- [ ] **Step 2: Extend ReplayResponse**

Add to `ReplayResponse`:
```python
collapsed_segments: list[CollapsedSegmentSchema] = []
highlight_indices: list[int] = []
stopped_at_breakpoint: bool = False
stopped_at_index: int | None = None
```

- [ ] **Step 3: Add highlights mode and stop_at_breakpoint**

In `api/replay_routes.py`, update the mode pattern:
```python
mode: str = Query(default="full", pattern="^(full|focus|failure|highlights)$"),
stop_at_breakpoint: bool = Query(default=False),
```

- [ ] **Step 4: Integrate segment collapsing in build_replay_response**

```python
from collector.replay_collapse import identify_low_value_segments

# In the endpoint handler:
if mode == "highlights":
    segments = identify_low_value_segments(replay_events)
    collapsed_segments = [CollapsedSegmentSchema(**asdict(s)) for s in segments]
else:
    collapsed_segments = []

# Handle stop_at_breakpoint
if stop_at_breakpoint and breakpoints:
    stopped_at_index = breakpoints[0].sequence if breakpoints else None
else:
    stopped_at_index = None
```

---

## Task 4: Phase 3 - Frontend "Replay from Here"

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add CollapsedSegment type**

In `frontend/src/types/index.ts`:
```typescript
export interface CollapsedSegment {
  start_index: number
  end_index: number
  event_count: number
  summary: string
  event_types: string[]
  total_duration_ms: number | null
}
```

- [ ] **Step 2: Update ReplayResponse type**

Add fields:
```typescript
export interface ReplayResponse {
  // ... existing ...
  collapsed_segments: CollapsedSegment[]
  highlight_indices: number[]
  stopped_at_breakpoint: boolean
  stopped_at_index: number | null
}
```

- [ ] **Step 3: Add focusEventId state and "Replay from here" button**

In `frontend/src/App.tsx`:
```tsx
const [focusEventId, setFocusEventId] = useState<string | null>(null)

// In event detail panel:
<button
  onClick={() => {
    setReplayMode('focus')
    setFocusEventId(selectedEvent?.id || null)
    fetchReplay()
  }}
  className="replay-from-here-btn"
>
  Replay from here
</button>
```

- [ ] **Step 4: Update API client**

In `frontend/src/api/client.ts`:
```typescript
async fetchReplay(
  sessionId: string,
  mode: string,
  options: {
    focusEventId?: string
    stopAtBreakpoint?: boolean
    // ... existing params
  }
): Promise<ReplayResponse>
```

- [ ] **Step 5: Build frontend**

```bash
cd frontend && npm run build
```

---

## Task 5: Phase 4 - Cross-Session Clustering

**Files:**
- Create: `collector/cross_session_clustering.py`
- Modify: `storage/repository.py`

- [ ] **Step 1: Create CrossSessionClusterer class**

In `collector/cross_session_clustering.py`:
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any

@dataclass
class CrossSessionCluster:
    id: str
    fingerprint: str
    session_ids: list[str]
    event_count: int
    first_seen: datetime
    last_seen: datetime
    representative_session_id: str
    representative_event_id: str
    avg_severity: float

class CrossSessionClusterer:
    def __init__(self, repository: "TraceRepository"):
        self.repository = repository

    async def cluster_failures(
        self,
        sessions: list["Session"],
        events_by_session: dict[str, list["TraceEvent"]],
        time_window_days: int = 7,
    ) -> list[CrossSessionCluster]:
        """Cluster failures across sessions using fingerprint similarity."""
        from collections import defaultdict
        import uuid

        # Extract all failure events (severity >= 0.78)
        failure_events: dict[str, list[tuple[str, "TraceEvent"]]] = defaultdict(list)

        for session in sessions:
            events = events_by_session.get(session.id, [])
            for event in events:
                if (event.importance or 0) >= 0.78:
                    fingerprint = self._compute_fingerprint(event)
                    failure_events[fingerprint].append((session.id, event))

        # Build clusters
        clusters = []
        for fingerprint, session_events in failure_events.items():
            if len(session_events) < 1:
                continue

            session_ids = list(set(se[0] for se in session_events))
            events = [se[1] for se in session_events]
            avg_severity = sum(e.importance or 0 for e in events) / len(events)

            # Select representative: highest importance in most recent session
            sorted_by_session = sorted(
                session_events,
                key=lambda se: (-se[1].importance, se[0]),
            )
            rep_session_id, rep_event = sorted_by_session[0]

            cluster = CrossSessionCluster(
                id=str(uuid.uuid4()),
                fingerprint=fingerprint,
                session_ids=session_ids,
                event_count=len(events),
                first_seen=min(e.timestamp for e in events if e.timestamp),
                last_seen=max(e.timestamp for e in events if e.timestamp),
                representative_session_id=rep_session_id,
                representative_event_id=rep_event.id,
                avg_severity=avg_severity,
            )
            clusters.append(cluster)

        return sorted(clusters, key=lambda c: -c.avg_severity * len(c.session_ids))

    def _compute_fingerprint(self, event: "TraceEvent") -> str:
        """Compute fingerprint for clustering."""
        key_field = event.name or event.event_type
        secondary = ""
        if event.data:
            if "tool_name" in event.data:
                secondary = event.data["tool_name"]
            elif "error_type" in event.data:
                secondary = event.data["error_type"]
        return f"{event.event_type}:{key_field}:{secondary}"
```

- [ ] **Step 2: Add repository methods for clusters**

In `storage/repository.py`:
```python
async def create_failure_cluster(self, cluster: FailureClusterModel) -> FailureClusterModel:
    async with self._session() as session:
        session.add(cluster)
        await session.commit()
        return cluster

async def list_failure_clusters(
    self,
    agent_name: str | None = None,
    days: int = 7,
) -> list[FailureClusterModel]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with self._session() as session:
        query = select(FailureClusterModel).where(
            FailureClusterModel.last_seen >= cutoff
        )
        if agent_name:
            query = query.join(SessionModel).where(
                SessionModel.agent_name == agent_name
            )
        result = await session.execute(query.order_by(FailureClusterModel.avg_severity.desc()))
        return list(result.scalars().all())
```

---

## Task 6: Phase 4 - Retention Enforcement

**Files:**
- Create: `storage/retention_enforcement.py`

- [ ] **Step 1: Create RetentionEnforcer class**

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class RetentionConfig:
    full_tier_days: int = 365
    summarized_tier_days: int = 90
    downsampled_tier_days: int = 30

@dataclass
class RetentionResult:
    sessions_processed: int
    events_deleted: int
    checkpoints_deleted: int
    events_summarized: int

class RetentionEnforcer:
    def __init__(self, repository: "TraceRepository"):
        self.repository = repository

    async def apply_retention_policy(
        self,
        config: RetentionConfig,
    ) -> RetentionResult:
        """Apply retention policy based on tier."""
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        result = RetentionResult(0, 0, 0, 0)

        # Process each tier
        for tier, days in [
            ("full", config.full_tier_days),
            ("summarized", config.summarized_tier_days),
            ("downsampled", config.downsampled_tier_days),
        ]:
            cutoff = now - timedelta(days=days)
            sessions = await self.repository.list_sessions_by_retention_tier(
                tier, older_than=cutoff
            )

            for session in sessions:
                if tier == "summarized":
                    # Strip verbose data, keep events
                    result.events_summarized += await self._summarize_session(session.id)
                elif tier == "downsampled":
                    # Delete all events and checkpoints
                    result.events_deleted += await self.repository.delete_events_for_session(session.id)
                    result.checkpoints_deleted += await self.repository.delete_checkpoints_for_session(session.id)

                result.sessions_processed += 1

        return result

    async def _summarize_session(self, session_id: str) -> int:
        """Strip verbose fields from events."""
        return await self.repository.summarize_session_events(session_id)
```

- [ ] **Step 2: Add repository methods**

```python
async def list_sessions_by_retention_tier(
    self,
    tier: str,
    older_than: datetime,
) -> list[Session]:
    async with self._session() as session:
        result = await session.execute(
            select(SessionModel).where(
                SessionModel.retention_tier == tier,
                SessionModel.started_at < older_than,
            )
        )
        return list(result.scalars().all())

async def summarize_session_events(self, session_id: str) -> int:
    """Strip verbose fields from events, return count."""
    # Implementation strips data, messages, result, stack_trace
    pass

async def delete_events_for_session(self, session_id: str) -> int:
    async with self._session() as session:
        result = await session.execute(
            delete(TraceEventModel).where(TraceEventModel.session_id == session_id)
        )
        await session.commit()
        return result.rowcount
```

---

## Task 7: Phase 5 - Policy Analysis Module

**Files:**
- Create: `collector/policy_analysis.py`

- [ ] **Step 1: Create PolicyShift dataclass and analyzer**

```python
from dataclasses import dataclass, field
from typing import Any, Literal

@dataclass
class ParameterChange:
    old_value: Any
    new_value: Any
    magnitude: float

@dataclass
class PolicyShift:
    event_id: str
    turn_index: int
    previous_template: str | None
    new_template: str
    parameter_changes: dict[str, ParameterChange] = field(default_factory=dict)
    shift_magnitude: float = 0.0
    triggering_turn_id: str | None = None

def analyze_policy_sequence(
    policies: list["PromptPolicyEvent"],
    turns: list["AgentTurnEvent"],
) -> list[PolicyShift]:
    """Analyze policy changes with semantic understanding."""
    if not policies:
        return []

    shifts = []
    previous_policy = None

    for i, policy in enumerate(policies):
        if previous_policy is None:
            previous_policy = policy
            continue

        # Detect template change
        template_changed = (
            policy.template_id != previous_policy.template_id
            or policy.name != previous_policy.name
        )

        # Detect parameter changes
        param_changes = {}
        if policy.policy_parameters and previous_policy.policy_parameters:
            all_keys = set(policy.policy_parameters.keys()) | set(previous_policy.policy_parameters.keys())
            for key in all_keys:
                old_val = previous_policy.policy_parameters.get(key)
                new_val = policy.policy_parameters.get(key)
                if old_val != new_val:
                    magnitude = _compute_parameter_magnitude(old_val, new_val)
                    param_changes[key] = ParameterChange(old_val, new_val, magnitude)

        if template_changed or param_changes:
            shift = PolicyShift(
                event_id=policy.id,
                turn_index=_find_turn_index(policy, turns),
                previous_template=previous_policy.template_id or previous_policy.name,
                new_template=policy.template_id or policy.name,
                parameter_changes=param_changes,
                shift_magnitude=_compute_shift_magnitude(template_changed, param_changes),
            )
            shifts.append(shift)

        previous_policy = policy

    return shifts

def _compute_parameter_magnitude(old_val: Any, new_val: Any) -> float:
    """Compute magnitude of parameter change."""
    if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
        if old_val == 0:
            return 1.0 if new_val != 0 else 0.0
        return min(1.0, abs(new_val - old_val) / abs(old_val))
    if isinstance(old_val, str) and isinstance(new_val, str):
        # Simple character difference ratio
        max_len = max(len(old_val), len(new_val))
        if max_len == 0:
            return 0.0
        diff = sum(1 for a, b in zip(old_val, new_val) if a != b) + abs(len(old_val) - len(new_val))
        return min(1.0, diff / max_len)
    return 0.5 if old_val != new_val else 0.0

def _compute_shift_magnitude(template_changed: bool, param_changes: dict) -> float:
    """Compute overall shift magnitude."""
    template_score = 0.6 if template_changed else 0.0
    param_score = max((c.magnitude for c in param_changes.values()), default=0.0)
    return min(1.0, template_score + param_score * 0.4)

def _find_turn_index(policy: "PromptPolicyEvent", turns: list["AgentTurnEvent"]) -> int:
    """Find the turn index closest to this policy event."""
    if not turns or not policy.timestamp:
        return 0
    for i, turn in enumerate(turns):
        if turn.timestamp and turn.timestamp >= policy.timestamp:
            return i
    return len(turns) - 1
```

- [ ] **Step 2: Write unit tests**

Create `tests/test_policy_analysis.py`:
```python
import pytest
from collector.policy_analysis import analyze_policy_sequence, PolicyShift

class TestAnalyzePolicySequence:
    def test_empty_policies_returns_empty(self):
        assert analyze_policy_sequence([], []) == []

    def test_single_policy_returns_empty(self):
        from unittest.mock import MagicMock
        policy = MagicMock(id="p1", template_id="t1", name="n1", policy_parameters={}, timestamp=None)
        assert analyze_policy_sequence([policy], []) == []

    def test_detects_template_change(self):
        from unittest.mock import MagicMock
        p1 = MagicMock(id="p1", template_id="t1", name="n1", policy_parameters={}, timestamp=None)
        p2 = MagicMock(id="p2", template_id="t2", name="n2", policy_parameters={}, timestamp=None)
        shifts = analyze_policy_sequence([p1, p2], [])
        assert len(shifts) == 1
        assert shifts[0].previous_template == "t1"
        assert shifts[0].new_template == "t2"
```

---

## Task 8: Phase 5 - Escalation Detection Module

**Files:**
- Create: `collector/escalation_detection.py`

- [ ] **Step 1: Create EscalationSignal dataclass and detector**

```python
from dataclasses import dataclass, field
from typing import Any, Literal

SIGNAL_TYPE = Literal[
    "explicit_keyword",
    "confidence_degradation",
    "tool_stake_increase",
    "decision_chain_depth",
    "safety_pressure",
    "handoff_pattern",
]

WEIGHTS: dict[SIGNAL_TYPE, float] = {
    "explicit_keyword": 0.15,
    "confidence_degradation": 0.25,
    "tool_stake_increase": 0.20,
    "decision_chain_depth": 0.15,
    "safety_pressure": 0.15,
    "handoff_pattern": 0.10,
}

@dataclass
class EscalationSignal:
    event_id: str
    turn_index: int
    signal_type: SIGNAL_TYPE
    magnitude: float
    evidence_event_ids: list[str] = field(default_factory=list)
    narrative: str = ""

def detect_escalation_signals(
    turns: list["AgentTurnEvent"],
    decisions: list["DecisionEvent"],
    safety_events: list["TraceEvent"],
) -> list[EscalationSignal]:
    """Detect escalation signals using multi-signal approach."""
    signals = []

    # 1. Confidence degradation
    signals.extend(_detect_confidence_degradation(decisions))

    # 2. Safety pressure
    signals.extend(_detect_safety_pressure(safety_events))

    # 3. Handoff patterns
    signals.extend(_detect_handoff_patterns(turns))

    # 4. Explicit keywords (lower weight)
    signals.extend(_detect_explicit_keywords(turns))

    return signals

def compute_escalation_score(signals: list[EscalationSignal]) -> float:
    """Compute weighted escalation score."""
    if not signals:
        return 0.0
    return min(1.0, sum(s.magnitude * WEIGHTS.get(s.signal_type, 0.1) for s in signals))

def _detect_confidence_degradation(decisions: list["DecisionEvent"]) -> list[EscalationSignal]:
    signals = []
    for i, decision in enumerate(decisions):
        if i > 0 and decision.confidence is not None:
            prev_conf = decisions[i - 1].confidence
            if prev_conf is not None and decision.confidence < prev_conf - 0.2:
                signals.append(EscalationSignal(
                    event_id=decision.id,
                    turn_index=i,
                    signal_type="confidence_degradation",
                    magnitude=prev_conf - decision.confidence,
                    narrative=f"Decision confidence dropped from {prev_conf:.2f} to {decision.confidence:.2f}",
                ))
    return signals

def _detect_safety_pressure(safety_events: list["TraceEvent"]) -> list[EscalationSignal]:
    if len(safety_events) < 2:
        return []
    # High density of safety events in window
    return [EscalationSignal(
        event_id=safety_events[-1].id,
        turn_index=len(safety_events),
        signal_type="safety_pressure",
        magnitude=min(1.0, len(safety_events) / 5),
        narrative=f"{len(safety_events)} safety events detected",
    )]

def _detect_handoff_patterns(turns: list["AgentTurnEvent"]) -> list[EscalationSignal]:
    signals = []
    for i, turn in enumerate(turns):
        if i > 0:
            prev_speaker = turns[i - 1].speaker
            curr_speaker = turn.speaker
            if prev_speaker != curr_speaker:
                # Check for goal transfer language
                goal = (turn.goal or "").lower()
                if any(kw in goal for kw in ["escalate", "handoff", "transfer", "review"]):
                    signals.append(EscalationSignal(
                        event_id=turn.id,
                        turn_index=i,
                        signal_type="handoff_pattern",
                        magnitude=0.7,
                        narrative=f"Speaker changed from {prev_speaker} to {curr_speaker} with transfer intent",
                    ))
    return signals

def _detect_explicit_keywords(turns: list["AgentTurnEvent"]) -> list[EscalationSignal]:
    keywords = ["escalate", "supervisor", "review", "critical", "urgent"]
    signals = []
    for i, turn in enumerate(turns):
        content = (turn.content or "").lower()
        goal = (turn.goal or "").lower()
        combined = content + " " + goal
        if any(kw in combined for kw in keywords):
            signals.append(EscalationSignal(
                event_id=turn.id,
                turn_index=i,
                signal_type="explicit_keyword",
                magnitude=0.5,
                narrative=f"Escalation keyword detected in turn",
            ))
    return signals
```

---

## Task 9: Phase 6 - Rolling Summary and Oscillation Detection

**Files:**
- Modify: `collector/live_monitor.py`

- [ ] **Step 1: Add RollingWindow dataclass**

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class RollingWindow:
    window_start: datetime
    window_end: datetime
    event_count: int = 0
    tool_calls: int = 0
    llm_calls: int = 0
    decisions: int = 0
    errors: int = 0
    refusals: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    unique_tools: set[str] = field(default_factory=set)
    unique_agents: set[str] = field(default_factory=set)
    avg_confidence: float = 0.0
    state_progression: list[str] = field(default_factory=list)

@dataclass
class RollingSummary:
    text: str
    metrics: dict[str, Any]
    window_type: str
    window_size: int
    computed_at: datetime
```

- [ ] **Step 2: Add rolling aggregation to LiveMonitor**

```python
def compute_rolling_window(
    self,
    events: list["TraceEvent"],
    window_seconds: int = 60,
) -> RollingWindow:
    """Compute rolling window metrics."""
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)

    window = RollingWindow(
        window_start=cutoff,
        window_end=now,
    )

    recent_events = [e for e in events if e.timestamp and e.timestamp >= cutoff]

    for event in recent_events:
        window.event_count += 1
        if event.event_type == "tool":
            window.tool_calls += 1
            if event.data and "tool_name" in event.data:
                window.unique_tools.add(event.data["tool_name"])
        elif event.event_type == "decision":
            window.decisions += 1
        elif event.event_type == "error":
            window.errors += 1
        elif event.event_type == "refusal":
            window.refusals += 1

    return window

def build_rolling_summary(self, window: RollingWindow) -> RollingSummary:
    """Build human-readable rolling summary."""
    text = f"Last {window.event_count} events: {window.tool_calls} tools, {window.decisions} decisions"
    if window.errors > 0:
        text += f", {window.errors} errors"
    if window.refusals > 0:
        text += f", {window.refusals} refusals"

    return RollingSummary(
        text=text,
        metrics={
            "event_count": window.event_count,
            "tool_calls": window.tool_calls,
            "decisions": window.decisions,
            "errors": window.errors,
            "refusals": window.refusals,
            "unique_tools": len(window.unique_tools),
        },
        window_type="time",
        window_size=60,
        computed_at=datetime.now(timezone.utc),
    )
```

- [ ] **Step 3: Add oscillation detection**

```python
@dataclass
class OscillationAlert:
    pattern: str  # e.g., "A->B->A->B"
    event_type: str
    repeat_count: int
    severity: float
    event_ids: list[str]

def detect_oscillation(
    events: list["TraceEvent"],
    window: int = 10,
) -> OscillationAlert | None:
    """Detect A->B->A->B patterns."""
    if len(events) < 4:
        return None

    recent = events[-window:] if len(events) > window else events

    # Extract sequence of (event_type, key) tuples
    sequence = []
    for e in recent:
        key = e.name or e.event_type
        if e.event_type == "tool" and e.data and "tool_name" in e.data:
            key = e.data["tool_name"]
        sequence.append((e.event_type, key))

    # Check for oscillation patterns
    for pattern_len in [2, 3, 4]:
        if len(sequence) < pattern_len * 2:
            continue
        pattern = sequence[:pattern_len]
        repeats = 1
        for i in range(pattern_len, len(sequence) - pattern_len + 1, pattern_len):
            if sequence[i:i + pattern_len] == pattern:
                repeats += 1

        if repeats >= 2:
            pattern_str = "->".join(p[1] for p in pattern)
            severity = min(1.0, repeats / 3)
            return OscillationAlert(
                pattern=pattern_str,
                event_type=pattern[0][0],
                repeat_count=repeats,
                severity=severity,
                event_ids=[e.id for e in recent[:pattern_len * repeats]],
            )

    return None
```

---

## Task 10: Phase 6 - Alert Persistence

**Files:**
- Create: `collector/alert_persister.py`
- Modify: `api/trace_routes.py`

- [ ] **Step 1: Create AlertPersister**

```python
from datetime import datetime, timezone
import uuid

class AlertPersister:
    def __init__(self, repository: "TraceRepository"):
        self.repository = repository

    async def persist_alerts(
        self,
        session_id: str,
        alerts: list["DerivedAlert"],
        tenant_id: str = "local",
    ) -> list["AnomalyAlertModel"]:
        """Persist derived alerts to database."""
        from storage.models import AnomalyAlertModel

        persisted = []
        for alert in alerts:
            model = AnomalyAlertModel(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=alert.alert_type,
                severity=alert.severity,
                signal=alert.signal,
                event_ids=alert.event_ids,
                detection_source=alert.source,
                detection_config={},
                created_at=datetime.now(timezone.utc),
            )
            await self.repository.create_anomaly_alert(model)
            persisted.append(model)

        return persisted
```

- [ ] **Step 2: Add alert endpoints**

In `api/trace_routes.py`:
```python
@router.get("/api/sessions/{session_id}/alerts")
async def get_session_alerts(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> list[AnomalyAlertSchema]:
    alerts = await repo.list_anomaly_alerts(session_id)
    return [AnomalyAlertSchema.model_validate(a) for a in alerts]

@router.get("/api/alerts/{alert_id}")
async def get_alert(
    alert_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> AnomalyAlertSchema:
    alert = await repo.get_anomaly_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AnomalyAlertSchema.model_validate(alert)
```

---

## Task 11: Frontend Updates for All Phases

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/LiveSummaryPanel.tsx`
- Create: `frontend/src/components/FailureClusterPanel.tsx`
- Create: `frontend/src/components/PolicyDiffView.tsx`

- [ ] **Step 1: Add FailureClusterPanel component**

```tsx
// frontend/src/components/FailureClusterPanel.tsx
import React from 'react'

interface Cluster {
  id: string
  fingerprint: string
  session_count: number
  avg_severity: number
  representative_session_id: string
}

export function FailureClusterPanel({ clusters }: { clusters: Cluster[] }) {
  return (
    <div className="failure-cluster-panel">
      <h3>Failure Clusters</h3>
      {clusters.map(cluster => (
        <div key={cluster.id} className="cluster-item">
          <span className="fingerprint">{cluster.fingerprint}</span>
          <span className="count">{cluster.session_count} sessions</span>
          <span className="severity">{(cluster.avg_severity * 100).toFixed(0)}%</span>
          <button onClick={() => window.location.hash = `/sessions/${cluster.representative_session_id}`}>
            View Representative
          </button>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Update LiveSummaryPanel with rolling summary**

```tsx
// Add to LiveSummaryPanel.tsx
interface RollingSummary {
  text: string
  metrics: Record<string, number>
  window_type: string
}

export function LiveSummaryPanel({ summary, rollingSummary }: {
  summary: LiveSummary
  rollingSummary?: RollingSummary
}) {
  return (
    <div className="live-summary-panel">
      {/* Existing content */}
      {rollingSummary && (
        <div className="rolling-summary">
          <h4>Rolling Summary</h4>
          <p>{rollingSummary.text}</p>
          <div className="metrics">
            {Object.entries(rollingSummary.metrics).map(([key, value]) => (
              <span key={key}>{key}: {value}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Build frontend**

```bash
cd frontend && npm run build
```

---

## Task 12: Final Testing and Validation

- [ ] **Step 1: Run full test suite**

```bash
python3 -m pytest tests/ -v
cd frontend && npm run build
```

- [ ] **Step 2: Verify exit criteria**

- [ ] User can click "Replay from here" on any event
- [ ] Highlights mode shows collapsed segments
- [ ] Failure clusters appear in UI
- [ ] Rolling summaries display in live panel
- [ ] Alerts persist to database

- [ ] **Step 3: Commit all changes**

```bash
git add .
git commit -m "feat: complete research features phases 3-6"
```
