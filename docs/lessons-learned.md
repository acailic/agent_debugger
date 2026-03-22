# Lessons Learned

This document captures what the repo teaches from actually trying to build an agent debugger, not just from the original design intent.

## 1. Event Design Comes First

The most important lesson is that debugger quality depends on event quality.

If the event schema is weak, the UI becomes guesswork. If the event schema is strong, many views become straightforward to build.

What that means here:

- `session_id` matters
- `parent_id` matters
- event type matters
- evidence and metadata matter
- checkpoints matter

The repo gets this mostly right.

## 2. Logs Are Not Enough

Plain logs are too low-level and too noisy for agent debugging.

What turns tracing into debugging is semantic structure:

- decision events
- tool call and result pairs
- model request and response pairs
- explicit errors
- replayable checkpoints

This repo shows why that distinction matters.

## 3. Async Context Handling Is Critical

Tracing agent systems often means tracing asynchronous code.

Without good context management, events lose their session identity or parent relationships. Using `contextvars` is one of the stronger design choices in the repo because it preserves execution context across async boundaries more cleanly than ad hoc global state.

## 4. Live Streaming Is Easy To Start And Hard To Finish

Getting live events into an in-memory buffer is relatively easy.

What is harder is making the live path and the historical path agree. This repo demonstrates that clearly:

- live event streaming can work before persistence is fully solved
- but a debugger product feels incomplete if streamed events and queried history are not the same truth

This is one of the most important implementation lessons in the codebase.

## 5. One Source Of Truth Matters

The repo currently shows what happens when session state and event flow are split across multiple concepts.

The lesson is simple:

- a debugging session should have one authoritative lifecycle

When session creation lives in one place and historical lookup lives in another, the whole system becomes harder to reason about.

## 6. Replay Is Mostly A State Problem

It is easy to say "time-travel debugging."

It is much harder to decide:

- what state gets checkpointed
- when checkpoints should be created
- how replay should resume
- how deterministic the replay path really is

This repo already contains the right intuition that checkpoints matter. The lesson from implementing it is that replay depends less on fancy UI and more on disciplined state modeling.

## 7. Frontend Quality Depends On Backend Honesty

A debugger UI only works well when backend data contracts are clear and stable.

This repo shows that even when the visualization ideas are good, the product still feels unfinished if:

- response shapes drift
- live and historical views disagree
- event payloads are not rich enough

The learning is that frontend progress depends on backend coherence.

## 8. The MVP Already Reveals The Right Product Shape

Even with the gaps, the repo already points to a good product shape:

- session list
- live trace timeline
- decision tree
- event detail panel
- replay from checkpoints

That is a useful lesson in itself. The repo does not need a completely different concept. It needs stronger execution on the same concept.

## 9. Research Is Most Useful When It Changes Product Decisions

The research papers linked in the docs are useful when they improve:

- event structure
- replay strategy
- evidence tracking
- safety observability
- multi-agent monitoring

They are less useful when they are treated as decoration.

The lesson is to convert research into product behavior, not just references.

## 10. The Right Next Step Is Integration, Not Expansion

The biggest practical learning from doing this so far is:

- the repo does not primarily need more concepts
- it needs tighter integration of the concepts it already has

The highest-value next move remains:

1. unify session lifecycle
2. unify live and persistent event flow
3. align backend contracts with the frontend
4. finish one complete debugger workflow

That is the shortest path from promising prototype to useful tool.
