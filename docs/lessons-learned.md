# Lessons Learned

This page is about what building this MVP has actually taught so far, not just what the original design said.

## 1. Event Design Comes First

The clearest lesson so far is that debugger quality depends on event quality.

If the event schema is vague, the UI turns into guesswork. If the event schema is clear, a lot of the UI becomes straightforward.

What that means here:

- `session_id` matters
- `parent_id` matters
- event type matters
- evidence and metadata matter
- checkpoints matter

The repo gets this mostly right.

## 2. Logs Are Not Enough

Plain logs are too low-level and too noisy for agent debugging.

What makes tracing feel like debugging is semantic structure:

- decision events
- tool call and result pairs
- model request and response pairs
- explicit errors
- replayable checkpoints

This repo shows why that distinction matters.

## 3. Async Context Handling Is Critical

Tracing agent systems often means tracing asynchronous code.

Without good context management, events lose their session identity or parent relationships. Using `contextvars` was one of the better design choices in this project because it preserves execution context across async boundaries without falling back to messy global state.

## 4. Live Streaming Is Easy To Start And Hard To Finish

Getting live events into an in-memory buffer is relatively easy.

What is harder is making the live path and the historical path agree. This project shows that very clearly:

- live event streaming can work before persistence is fully solved
- but a debugger product feels incomplete if streamed events and queried history are not the same truth

This is one of the most important implementation lessons in the codebase.

## 5. One Source Of Truth Matters

This codebase is a good example of what happens when session state and event flow are split across multiple concepts.

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

The repo already has the right instinct that checkpoints matter. The lesson from implementation is that replay depends less on clever UI and more on disciplined state modeling.

## 7. Frontend Quality Depends On Backend Honesty

A debugger UI only works well when backend data contracts are clear and stable.

This repo shows that even when the UI ideas are good, the product still feels unfinished if:

- response shapes drift
- live and historical views disagree
- event payloads are not rich enough

The learning is that frontend progress depends on backend coherence.

## 8. The MVP Already Reveals The Right Product Shape

Even with the current gaps, the product shape is already visible:

- session list
- live trace timeline
- decision tree
- event detail panel
- replay from checkpoints

That matters because the project does not need a completely different concept. It needs stronger execution on the same concept.

## 9. Research Is Most Useful When It Changes Product Decisions

The papers linked in the docs are useful when they change product decisions around:

- event structure
- replay strategy
- evidence tracking
- safety observability
- multi-agent monitoring

They are much less useful when they are treated as decoration.

The lesson is to convert research into product behavior, not just references.

## 10. The Right Next Step Is Integration, Not Expansion

The biggest practical lesson so far is:

- the repo does not primarily need more concepts
- it needs tighter integration of the concepts it already has

The highest-value next move is still:

1. unify session lifecycle
2. unify live and persistent event flow
3. align backend contracts with the frontend
4. finish one complete debugger workflow

That is still the shortest path from promising prototype to useful tool.
