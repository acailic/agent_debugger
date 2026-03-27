# Collector Module Refactoring Design

**Date:** 2026-03-27
**Status:** Approved
**Scope:** `collector/intelligence.py`, `collector/live_monitor.py`

## Context

The collector module contains two large, complex files that handle session analysis and live monitoring:

- `intelligence.py` (433 lines) - Session-level trace analysis with `analyze_session()` at 190 lines
- `live_monitor.py` (422 lines) - Real-time monitoring with `build_live_summary()` at 193 lines

These methods mix multiple responsibilities (ranking, clustering, alert derivation, summary building), making them hard to test, understand, and modify independently. The codebase has good test coverage, so we can refactor with confidence.

**Goals:**
1. Reduce complexity by extracting focused services
2. Improve testability through isolated components
3. Maintain 100% backward API compatibility via facade pattern

## Architecture

### `live_monitor.py` Refactoring

**Target structure:**
```
collector/
├── live_monitor.py          # Facade (unchanged public API)
├── alerts/
│   ├── __init__.py          # Exports all alerters
│   ├── base.py              # AlertDeriver protocol
│   ├── tool_loop.py         # ToolLoopAlerter
│   ├── guardrail.py         # GuardrailPressureAlerter
│   ├── policy_shift.py      # PolicyShiftAlerter
│   └── strategy_change.py   # StrategyChangeAlerter
├── rolling.py               # RollingWindowCalculator
└── models.py                # (existing - no changes)
```

**New components:**

| Module | Class | Responsibility |
|--------|-------|---------------|
| `alerts/base.py` | `AlertDeriver` | Protocol with `derive(events: list[TraceEvent]) -> list[dict]` |
| `alerts/tool_loop.py` | `ToolLoopAlerter` | Detect 3+ consecutive same-tool calls |
| `alerts/guardrail.py` | `GuardrailPressureAlerter` | Detect multiple refusals/policy violations in recent window |
| `alerts/policy_shift.py` | `PolicyShiftAlerter` | Detect multiple active prompt policies |
| `alerts/strategy_change.py` | `StrategyChangeAlerter` | Detect decision action shifts between consecutive decisions |
| `rolling.py` | `RollingWindowCalculator` | `compute_rolling_window()`, `build_rolling_summary()` |

**Refactored `LiveMonitor`:**
```python
class LiveMonitor:
    def __init__(self):
        self._alert_derivers: list[AlertDeriver] = [
            ToolLoopAlerter(),
            GuardrailPressureAlerter(),
            PolicyShiftAlerter(),
            StrategyChangeAlerter(),
        ]

    def compute_rolling_window(self, events, window_seconds=60) -> RollingWindow:
        return RollingWindowCalculator.compute(events, window_seconds)

    def build_rolling_summary(self, window) -> RollingSummary:
        return RollingWindowCalculator.build_summary(window)

    def build_live_summary(self, events, checkpoints) -> dict:
        if not events:
            return self._empty_summary(checkpoints)

        # Extract latest events by type
        latest = self._extract_latest_events(events)

        # Compute rolling metrics
        window = self.compute_rolling_window(events)
        rolling = self.build_rolling_summary(window)

        # Derive alerts from all alerters
        recent_alerts = []
        for deriver in self._alert_derivers:
            recent_alerts.extend(deriver.derive(events[-12:]))

        # Add captured behavior alerts
        recent_alerts.extend(self._extract_behavior_alerts(events[-12:]))

        # Detect oscillation
        oscillation_alert = detect_oscillation(events)

        # Compute checkpoint deltas
        checkpoint_deltas = self.compute_checkpoint_deltas(checkpoints, events)

        return self._build_response(
            events, checkpoints, latest, rolling, recent_alerts,
            oscillation_alert, checkpoint_deltas
        )
```

### `intelligence.py` Refactoring

**Target structure:**
```
collector/
├── intelligence.py          # Facade (unchanged public API)
├── ranking/
│   ├── __init__.py          # Exports
│   ├── event_ranker.py      # EventRankingService
│   └── checkpoint_ranker.py # CheckpointRankingService
├── clustering/
│   ├── __init__.py
│   └── failure_clusters.py  # FailureClusterAnalyzer
└── highlights.py            # generate_highlights() (moved from intelligence.py)
```

**New components:**

| Module | Class | Responsibility |
|--------|-------|---------------|
| `ranking/event_ranker.py` | `EventRankingService` | Compute severity, novelty, recurrence, replay_value per event |
| `ranking/checkpoint_ranker.py` | `CheckpointRankingService` | Compute restore_value and retention_tier per checkpoint |
| `clustering/failure_clusters.py` | `FailureClusterAnalyzer` | Fingerprint events, cluster by fingerprint, pick representatives |
| `highlights.py` | — | `generate_highlights()` function (move from intelligence.py) |

**Refactored `TraceIntelligence.analyze_session()`:**
```python
def analyze_session(self, events: list[TraceEvent], checkpoints: list[Checkpoint]) -> dict:
    if not events:
        return self._empty_result()

    # Step 1: Compute event rankings
    rankings = self._event_ranker.rank_events(
        events=events,
        fingerprint_fn=self.fingerprint,
        severity_fn=self.severity,
    )

    # Step 2: Cluster failures
    clusters = self._clusterer.cluster_failures(rankings)

    # Step 3: Rank checkpoints
    checkpoint_rankings = self._checkpoint_ranker.rank_checkpoints(
        checkpoints, rankings
    )

    # Step 4: Compute session-level metrics
    session_replay_value = self._compute_session_replay_value(
        rankings, clusters, checkpoint_rankings, events
    )
    retention_tier = self.retention_tier(
        replay_value=session_replay_value,
        high_severity_count=sum(1 for r in rankings if r["severity"] >= 0.9),
        failure_cluster_count=len(clusters),
        behavior_alert_count=len(self._extract_behavior_alerts(rankings)),
    )

    # Step 5: Generate explanations and highlights
    failure_explanations = self._diagnostics.build_failure_explanations(
        events, {r["event_id"]: r for r in rankings}, self.event_headline
    )
    highlights = generate_highlights(events, rankings, self.event_headline)

    return {
        "event_rankings": rankings,
        "failure_clusters": clusters,
        "representative_failure_ids": [c["representative_event_id"] for c in clusters],
        "high_replay_value_ids": self._select_high_replay_ids(rankings),
        "behavior_alerts": self._extract_behavior_alerts(rankings),
        "checkpoint_rankings": checkpoint_rankings,
        "session_replay_value": round(session_replay_value, 4),
        "retention_tier": retention_tier,
        "session_summary": self._build_session_summary(rankings, clusters, checkpoints),
        "failure_explanations": failure_explanations,
        "live_summary": self.build_live_summary(events, checkpoints),
        "highlights": highlights,
    }
```

## API Compatibility

**All existing imports continue to work:**
```python
from collector import TraceIntelligence, LiveMonitor
from collector.intelligence import generate_highlights, Highlight
from collector.live_monitor import RollingWindow, RollingSummary
```

**No changes to:**
- `collector/__init__.py` exports
- Method signatures on `TraceIntelligence` or `LiveMonitor`
- Return types from public methods

## Migration Steps

1. Create `collector/alerts/` directory with base protocol and alerters
2. Create `collector/rolling.py` with `RollingWindowCalculator`
3. Wire alerters and calculator into `LiveMonitor`
4. Run tests, verify `LiveMonitor` behavior unchanged
5. Create `collector/ranking/` directory with ranker services
6. Create `collector/clustering/` directory with cluster analyzer
7. Move `generate_highlights()` to `collector/highlights.py`
8. Wire rankers and clusterer into `TraceIntelligence`
9. Run tests, verify `TraceIntelligence` behavior unchanged
10. Remove extracted code from original files

## Verification

- `ruff check .` - no lint errors
- `.venv/bin/python -m pytest -q` - all 1061 tests pass
- Manual verification of `/api/sessions/{id}/analysis` endpoint
- Manual verification of `/api/sessions/{id}/live` endpoint

## Files Changed

| File | Action |
|------|--------|
| `collector/alerts/__init__.py` | Create |
| `collector/alerts/base.py` | Create |
| `collector/alerts/tool_loop.py` | Create |
| `collector/alerts/guardrail.py` | Create |
| `collector/alerts/policy_shift.py` | Create |
| `collector/alerts/strategy_change.py` | Create |
| `collector/rolling.py` | Create |
| `collector/ranking/__init__.py` | Create |
| `collector/ranking/event_ranker.py` | Create |
| `collector/ranking/checkpoint_ranker.py` | Create |
| `collector/clustering/__init__.py` | Create |
| `collector/clustering/failure_clusters.py` | Create |
| `collector/highlights.py` | Create |
| `collector/live_monitor.py` | Modify |
| `collector/intelligence.py` | Modify |
