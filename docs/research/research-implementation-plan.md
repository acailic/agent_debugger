# Research Implementation Plan

This page turns the paper-inspired direction in this repo into an execution plan.

It is not a literature review. It is a build plan.

## Goal

Move `agent_debugger` from "research-informed tracing base" to a debugger that deeply exposes:

- evidence-grounded decisions
- safety and refusal behavior
- prompt-policy and multi-agent control surfaces
- replay worth using
- real-time monitoring for long-running agents
- root-cause analysis over failures
- explanation layers over raw execution traces
- failure-aware memory for repair and regression work
- guided exploration across large trace graphs

## Current State

The repo now has a stronger event model and a coherent runtime path:

- structured decisions with evidence and provenance
- safety, refusal, policy, prompt-policy, agent-turn, and behavior-alert events
- database-backed session/event/checkpoint persistence in the main runtime path
- normalized trace, analysis, and replay endpoints
- improved importance scoring over structured event fields
- a working frontend debugger shell

The main remaining gap is not "more ideas." It is productizing those ideas through:

1. deeper replay behavior
2. richer UI workflows
3. evaluation and retention logic
4. cross-session analysis

This page is intentionally research-feature focused.

For the current platform and cloud-readiness state, use:

- [Progress](./progress.md)
- [Architecture](./architecture.md)
- [Improvement Roadmap](./improvement-roadmap.md)

## Research Themes To Implement

### 1. Neural Debugger Pattern

Source pressure:

- focused replay
- breakpoints
- inspect-state actions
- debugger-native interaction

What belongs in this repo:

- selective replay around one decision or error
- replay breakpoints by event type, tool, safety outcome, or confidence threshold
- event-to-state inspection panel
- "focus from here" workflow

### 2. MSSR / Adaptive Replay

Source pressure:

- replay should prefer high-value traces
- retention should not be FIFO

What belongs in this repo:

- session-level replay ranking
- smarter checkpoint selection
- retention tiers
- anomaly clustering and representative failure selection

### 3. Evidence-Grounded Reasoning

Source pressure:

- decisions should show why they happened
- evidence should be traceable to upstream events

What belongs in this repo:

- decision provenance panel
- explicit weak or missing evidence markers
- grounded-decision prioritization in UI and ranking

### 4. Act-Or-Refuse Safety

Source pressure:

- refusal is not an error
- guardrails should be observable

What belongs in this repo:

- safety-check timeline states
- refusal-aware replay
- guarded vs executed action filters
- policy violation summaries

### 5. Policy-Parameterized Prompts / Multi-Agent Control

Source pressure:

- prompts are control surfaces
- multi-agent sessions need more than a flat message log

What belongs in this repo:

- prompt-policy metadata on LLM request flows
- speaker and turn identity
- agent-to-agent conversation view
- compare sessions under different prompt-policy settings

### 6. Real-Time Agent Monitoring

Source pressure:

- proactive systems need live state summaries
- long sessions need anomaly detection

What belongs in this repo:

- live session summary panel
- rolling state summary
- oscillation / loop alerts
- recent checkpoint visibility

### 7. Root Cause Analysis / Causal Trace Reconstruction

Source pressure:

- failures should be traceable backward through causal dependencies
- long traces need ranked suspects, not only chronological review

What belongs in this repo:

- causal edges between decisions, tool calls, evidence, checkpoints, and error events
- "why did this fail?" drill-down from a failure to upstream candidates
- ranked root-cause hypotheses with visible confidence
- causal overlays in replay and event detail views

### 8. Failure Explanations For Coding Agents

Source pressure:

- raw traces are too expensive to interpret under time pressure
- explanations should stay linked to evidence, not replace it

What belongs in this repo:

- explanation cards that summarize symptom, likely cause, evidence, and next inspection point
- a normalized taxonomy for common failure modes
- session summaries that distinguish surface error from deeper failure mechanism
- side-by-side raw trace and explanation views

### 9. Failure-Aware Repair Memory

Source pressure:

- failed repair attempts are valuable training and debugging data
- debugging systems should remember what was already tried

What belongs in this repo:

- explicit repair-attempt events with outcome and artifact links
- summaries of repeated failed strategies across sessions
- session and cluster views that show prior failed fixes before a new attempt
- ranking by repair-learning value, not only failure severity

### 10. Exploratory Search Over Large Trace Graphs

Source pressure:

- large unknown spaces need frontier-based exploration
- exploration plans should adapt as new evidence appears

What belongs in this repo:

- branch and checkpoint frontier scoring for selective inspection
- "show me the next most informative branch" workflows
- exploration-aware decision tree traversal instead of only manual expansion
- receding-horizon navigation across long, branching sessions

## Delivery Plan

### Phase 1: Contract And Query Cleanup

Status:
completed

Objective:
make the richer event model actually consumable.

Tasks:

- align all query endpoints with the persisted event schema
- normalize backend response shapes for sessions, traces, trees, checkpoints, and replay
- add filters for event type, failure state, safety state, and importance
- add query support for high-value sessions and high-value checkpoints
- expose prompt-policy and provenance fields in API payloads

Exit criteria:

- one session can be queried consistently from DB-backed endpoints
- frontend can consume one canonical event shape
- safety/refusal/provenance fields survive capture, persistence, and query

### Phase 2: One Complete Research-Backed Debugger Flow

Status:
mostly complete

Objective:
ship one workflow that feels like a debugger, not just a log viewer.

Tasks:

- build session list
- build timeline with safety/refusal/provenance indicators
- build event detail panel
- build decision provenance panel
- build decision tree using the real event hierarchy
- support selecting an event and jumping to nearby checkpoints

Exit criteria:

- user can inspect a decision and answer:
  - what happened
  - why it happened
  - which evidence justified it
  - whether a policy or safety mechanism intervened

### Phase 3: Selective Replay

Status:
partially complete

Objective:
make replay useful and focused.

Tasks:

- implement replay entrypoints from error, decision, refusal, or checkpoint
- add replay breakpoints by event type, tool name, confidence threshold, and safety outcome
- show nearest checkpointed state beside replay timeline
- collapse low-value segments during replay
- keep blocked and refused actions visible in replay

Exit criteria:

- user can choose one interesting event and replay only the relevant branch
- replay can stop automatically on configured breakpoints

### Phase 4: Adaptive Ranking And Retention

Status:
partially complete

Objective:
turn static importance into useful operational memory.

Tasks:

- compute session-level replay value
- incorporate rarity, recurrence, cost, severity, and reuse value
- rank checkpoints for comparison and restore value
- define retention tiers:
  - full retention
  - summarized retention
  - downsampled retention
- cluster repeated failures and keep representative traces

Exit criteria:

- session list can be sorted by replay value, not just recency
- retention policy distinguishes routine runs from high-value failures

### Phase 5: Multi-Agent And Prompt-Policy Views

Status:
partially complete in the UI

Objective:
make policy and coordination visible.

Tasks:

- add conversation view for agent turns
- visualize speaker, role, turn goal, and policy context
- compare two runs with different prompt-policy settings
- add session metrics:
  - escalation frequency
  - repetition
  - evidence use
  - stance shift

Exit criteria:

- multi-agent traces are understandable without reading raw payloads
- prompt-policy changes can be compared across runs

Implemented so far:

- single-session conversation panel for `agent_turn` events
- prompt-policy visibility linked to later turns
- speaker and turn goal visibility in the console
- two-session comparison view for prompt-policy and coordination deltas
- heuristic comparison metrics for stance shifts, escalations, and grounded decisions

Still missing:

- benchmarked session-to-session prompt-policy comparison semantics
- stronger non-heuristic stance-shift and escalation metrics
- stronger derived summaries over turn sequences

### Phase 6: Real-Time Monitoring And Alerts

Status:
partially complete in the UI

Objective:
make long-running sessions observable while they are active.

Tasks:

- build live session summary panel
- surface latest decision, latest tool activity, latest safety state, latest checkpoint
- detect repeated tool loops, oscillation, and abrupt strategy changes
- emit and display behavior alerts
- add rolling summaries for long traces

Exit criteria:

- active sessions can be monitored without reading the full event stream
- unstable or suspicious behavior is surfaced proactively

Implemented so far:

- behavior alerts in the main console
- SSE subscription path in the frontend
- live session pulse panel with latest decision, tool, safety, turn, policy, and checkpoint context
- derived live anomaly timeline for loops, guardrail pressure, policy shifts, and strategy changes
- backend live summary endpoint consumed by the frontend live monitor

Still missing:

- stronger derived rolling summaries
- explicit loop and oscillation alert timelines
- richer active-session checkpoint updates
- persisted live anomaly history and stronger backend-native scoring depth

## Prioritized Next Tasks

If work continues immediately, the best order is:

1. strengthen replay restore semantics beyond checkpoint slicing
2. add failure-to-cause drill-down with ranked root-cause hypotheses
3. generate structured failure explanation cards linked to source events
4. add seeded benchmark corpora and UI smoke workflows around them
5. expand replay ranking into cross-session clustering and retention tiers
6. build multi-agent and prompt-policy comparison views
7. add live monitoring summaries and anomaly drill-down

## Parallel Platform Track

Research features are no longer the only meaningful next work.

A parallel platform track is now clearly active:

1. finish cloud/auth wiring around the accepted ADRs
2. enforce tenant isolation in storage and repository code
3. wire redaction into ingestion and persistence
4. complete database configuration and migration support

That platform track is not a distraction from the research plan. It is what makes the research-backed debugger viable outside a strong local demo.

## Non-Goals

This repo should not:

- try to reproduce full paper training methods
- store unrestricted chain-of-thought
- add speculative complexity before one complete workflow ships
- treat the debugger itself as the safety system

## Definition Of Done

The research direction is being used well when:

- papers change product behavior, not only docs
- a refusal is distinct from an error in trace review
- a decision can be traced back to evidence-producing events
- a failure can be traced back to plausible upstream causes
- raw traces can be compressed into explanations without losing evidence links
- replay starts from the right boundary instead of replaying everything
- prompt-policy changes are observable and comparable
- long-running sessions surface alerts before a user reads thousands of events
