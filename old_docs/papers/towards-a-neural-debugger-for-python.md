# Towards a Neural Debugger for Python

Paper: [arXiv:2603.09951v1](https://arxiv.org/abs/2603.09951v1)

## Core Idea

This paper argues that code models should not only predict program execution, but should also support debugger-like interaction. The core idea is moving from passive execution-trace prediction toward active debugging behaviors such as breakpoints and stepping through code.

## Why It Matters Here

The important shift is simple:

- execution traces alone are not enough
- debugging becomes useful when the user can act on the trace

That matters for this repo because agent debugging should not stop at "show me the trace." It should move toward "let me inspect, pause, focus, and reason over the trace at the right boundary."

## Key Takeaways For The Repo

### 1. Debugger actions should become first-class events

Right now the repo mostly captures runtime events from the agent. A stronger debugger would also model inspection actions such as:

- set breakpoint
- step into
- step over
- step out
- inspect state
- compare before/after state

These do not need to be neural to be useful. The product benefit comes from representing the actions explicitly.

### 2. Replay should become selective, not just chronological

The paper emphasizes focused execution around relevant code regions. The equivalent here is:

- replay only the critical branch
- replay around an error
- replay from a checkpoint near the failure
- collapse low-value segments

This would make trace review much more practical than scrolling through every event.

### 3. State inspection matters as much as event order

An event timeline is necessary but not sufficient. The debugger becomes much better when each interesting event can expose:

- current tool inputs
- outputs
- model response metadata
- decision evidence
- checkpointed state snapshots

## Concrete Opportunities

- add a "focus from here" replay mode
- add user-defined breakpoints on event type, tool name, or confidence threshold
- add event-to-state inspection panes
- add step controls for walking event-by-event through a session

## Caution

This paper is about code execution and debugger-like model behavior, not directly about generic agent tracing. The useful lesson is the interaction model, not the assumption that this repo should become a neural interpreter itself.

## Best Next Experiment

Implement one selective replay flow:

- choose an error or decision event
- jump to that point
- step forward event by event
- show the nearest checkpointed state beside the trace
