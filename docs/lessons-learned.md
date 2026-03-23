# Lessons Learned

This page is about what building the debugger has actually taught so far, not just what the original design said.

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

What is harder is making the live path and the historical path agree. This project showed that very clearly:

- live event streaming can work before persistence is fully solved
- but a debugger product feels incomplete if streamed events and queried history are not the same truth

That lesson has now been applied: the buffer is the live fan-out path and the repository is the durable truth.

## 5. One Source Of Truth Matters

This codebase is a good example of what happens when session state and event flow are split across multiple concepts.

The lesson is simple:

- a debugging session should have one authoritative lifecycle

When session creation lives in one place and historical lookup lives in another, the whole system becomes harder to reason about. The database-backed repository is the right authority here; in-memory helpers should stay helpers.

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

This repo showed that even when the UI ideas are good, the product still feels unfinished if:

- response shapes drift
- live and historical views disagree
- event payloads are not rich enough

The learning is that frontend progress depends on backend coherence. Once the contract layer was normalized, the UI became much easier to assemble into a real debugger surface.

## 8. The Core Debugger Shape Was Right Early

Even before the stack was fully coherent, the product shape was already visible:

- session list
- live trace timeline
- decision tree
- event detail panel
- replay from checkpoints

That mattered because the project did not need a different concept. It needed stronger execution on the same concept.

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

The biggest practical lesson was:

- the repo does not primarily need more concepts
- it needs tighter integration of the concepts it already has

That integration work is mostly done now. The highest-value next move is:

1. deepen replay from trace slicing into stronger state restoration
2. expand benchmark corpora and demo seed data
3. improve clustering, ranking, and cross-session comparison
4. harden the product for auth, retention, and redaction

That is now the shortest path from working debugger core to research-grade tool.

## 11. Configuration Before Transport Was The Right Order

Adding `agent_debugger.init()` before finishing cloud transport was a good sequencing decision.

It created one clear place for:

- API key resolution
- endpoint selection
- enable/disable behavior
- sampling and redaction settings

That matters because cloud support will be much easier to reason about with one config surface instead of ad hoc environment lookups spread across the runtime.

## 12. Security Features Are Only Real When They Sit On The Hot Path

This round of work made an important distinction visible:

- having auth helpers is progress
- having a redaction pipeline is progress
- but neither counts as a finished product capability until every ingest and query path actually uses them

That is a useful lesson because it prevents the docs from overstating maturity.

The implementation now has the right building blocks. What is still missing is end-to-end enforcement.

## 13. Extraction Work Pays Off Right Before Scale Work

Extracting ORM models and introducing `BufferBase` were not flashy changes, but they were the right kind of preparation.

They reduce coupling in exactly the places that need to change next:

- storage models for tenancy and migrations
- event buffering for local vs cloud fan-out

The lesson is that infrastructure-facing refactors are highest value when they remove friction from the next concrete product step.
