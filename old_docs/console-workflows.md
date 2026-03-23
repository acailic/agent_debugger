# Console Workflows

This page documents the debugger workflows that are actually implemented in the
current console.

It is intentionally narrower than the research plan. This is the "what can I
do today?" page.

## Current Workflows

### 1. Session Prioritization

The session rail can now be sorted by:

- replay value
- recency

Each session card surfaces:

- replay value
- retention tier
- base session health metrics

This means high-value failures and unusual runs can be surfaced before routine
traffic.

### 2. Provenance Inspection

The event detail panel supports:

- evidence provenance links
- upstream context links
- related event links
- direct "focus replay" from the current event

This is the main evidence-grounded debugging workflow right now.

### 3. Selective Replay

Replay now supports:

- full session replay
- focused replay from a chosen event
- failure replay from the latest failure signal
- breakpoints by event type, tool, confidence, and safety outcome

Focused replay is branch-aware. It no longer replays the entire session suffix
when a single branch is selected.

### 4. Checkpoint Comparison

Checkpoint rankings are visible in the console and can be used as restore
candidates.

The checkpoint panel supports:

- ranked checkpoint selection
- restore-value comparison
- inspect the event linked to a checkpoint
- launch focus replay from that checkpoint's event
- compare selected checkpoint state with the current replay anchor

This is the repo's first real retention-aware debugging workflow.

### 5. Prompt Policy And Multi-Agent Coordination

The coordination panel now surfaces:

- prompt-policy events
- agent-turn events
- speaker identities
- turn goals
- turn content
- active policy attached to later turns

This is not yet a full cross-session comparison system, but it makes one
session's multi-agent coordination understandable without reading raw JSON.

### 6. Cross-Session Prompt Policy Comparison

The console can now compare a primary session with a second session and surface:

- replay value and retention tier side by side
- turn count deltas
- prompt-policy count deltas
- speaker topology deltas
- heuristic stance-shift counts
- heuristic escalation counts
- grounded-decision count deltas
- policy template and speaker set differences

The current comparison is heuristic and UI-local. It is meant to make runs
comparable quickly, not to act as a final evaluation benchmark.

### 7. Live Session Pulse

The console now subscribes to the session SSE stream and surfaces a live summary
panel with:

- connection state
- live event count
- latest decision
- latest tool activity
- latest safety intervention
- latest agent turn
- latest prompt policy
- latest checkpoint
- rolling summary text from the newest available state summary or reasoning
- backend-derived anomaly signals from the recent event window
- a live alert timeline mixing captured `behavior_alert` events with backend-derived instability alerts

The live panel is backed by a dedicated server-side summary endpoint, not only
client-side heuristics. It is still light, but it makes active sessions
understandable without manually tailing raw events.

## What Is Still Missing

The console is stronger, but not complete.

Notable gaps:

- stronger benchmarked stance-shift and escalation metrics across sessions
- collapse low-value replay segments automatically
- richer live rolling state summaries for active runs
- persisted live anomaly history and stronger backend-native scoring
- retention actions that affect storage policy instead of only labeling traces

## Best Current Demo Path

If you want to see the strongest path in the console today:

1. Sort sessions by replay value.
2. Open a high-retention session.
3. Pick a clustered failure or a ranked checkpoint.
4. Run focus replay.
5. Use event provenance links to inspect upstream evidence.
6. Review the coordination panel to see speaker turns and active prompt policy.
7. Pick a comparison session to diff speaker and prompt-policy behavior.
8. Watch the live session pulse while new events stream in.

That path is the closest thing in the repo right now to the research-inspired
debugger described in the paper notes.
