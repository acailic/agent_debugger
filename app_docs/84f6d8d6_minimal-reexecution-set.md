# Minimal Re-execution Set (roadmap M2.1)

## What changed and why

For any suspect decision in a session audit you can now ask: *what is the smallest sub-graph that would have to re-run to confirm or invalidate this decision's claim?* The answer is computed deterministically — no LLM, no I/O, no clock, no randomness — and served as a first-class audit surface:

```
GET /api/sessions/{session_id}/decisions/{event_id}/reexecution-set
```

This is roadmap item M2.1 from the provenance survey note (`docs/papers/from-agent-traces-to-trust-provenance-survey.md`). The endpoint is a planning layer only: it names what *would* re-run; it never executes anything. Nothing was added to the frontend, the trust score, claim verification statuses, or the existing justification / evidence-graph endpoints.

## The computation

`build_reexecution_set(events, report, event_id)` in `collector/audit/reexecution.py` is a pure function of the session's trace events, the audit report dict from `SessionAuditEngine.audit(...)`, and the decision's event id. It returns `None` when the id does not resolve to a captured decision claim — the route maps that to a 404, same as the justification route.

Every set member carries an event id, a role, a mode, and a one-line `why_included` reason:

| Role | Who gets it |
|---|---|
| `decision` | the suspect decision itself |
| `evidence` | every cited event in the claim's `evidence_refs` that resolves to a trace event (resolved tool results / user inputs / retrieved facts) |
| `upstream_tool_call` | direct parent refs of an evidence node that are `TOOL_CALL` events — the invocations that would have to be re-made |
| `downstream` | the decision's full causal subtree (children index walk, 2000-iteration bound as a cycle guard only — no size cap) |

Role precedence is `decision > evidence > upstream_tool_call > downstream`; an id keeps the first role it is assigned.

Mode is `required_rerun` for the decision and upstream tool calls, and for evidence/downstream nodes unless their event type is `AGENT_TURN`/`AGENT_START` — operator-supplied input is marked `read_only` (re-supplied verbatim, not re-executed).

The payload also carries edges between included nodes, reusing the evidence-graph semantics by importing the engine's own helpers (`_build_children_index`, `_iso`, `_source_class_for` from `collector/audit/audit_engine.py`, `event_label` from `collector/intelligence/helpers.py`):

- **evidence edges** — decision → each cited evidence node, with `source_class` from the same logic `build_evidence_graph` uses (`tool_backed` / `user_provided` / `other`);
- **causal edges** — parent → node for every included node whose parent refs are also in the set.

Determinism is structural, not incidental: nodes are sorted by trace position, evidence edges follow the claim's `evidence_refs` order, causal edges follow node trace order × captured parent-ref order, and no output order ever comes from set iteration. A compact markdown summary (required-reruns, read-only, edges — sections always emitted) ships alongside.

## Files that carry it

- `collector/audit/reexecution.py` — new module; `build_reexecution_set` plus private helpers (`_parent_refs`, `_descendants`, `_mode_for`, `_node`, `_why_included`, `_markdown`). In the style of `collector/audit/failure_narrative.py`.
- `collector/audit/__init__.py` — exports `build_reexecution_set`.
- `api/audit_routes.py` — new route `get_decision_reexecution_set`, placed directly after `get_decision_justification`, mirroring its `require_session` → `analyze_session` → audit → commit/rollback structure and recording a `decision_reexecution_set_viewed` event.
- `api/schemas_analysis.py` — `ReexecutionNodeSchema`, `ReexecutionEdgeSchema`, `ReexecutionSetSchema`, `ReexecutionSetResponse` (inserted after `DecisionJustificationResponse`).
- `tests/test_reexecution.py` — unit tests for the builder and route tests via `create_app` + httpx `ASGITransport`, using the `_event`/`_decision` helper conventions from `tests/test_failure_narrative.py`.
- `specs/84f6d8d6_minimal-reexecution-set.md` — the build plan this change implements.
- `adws/adw_modules/quality.py` — ADW harness, not product code: the quality phase's `test`/`lint` blocks were wired from placeholders to the repo convention (`.venv-ci/bin/pytest -q`, `.venv-ci/bin/ruff check .`), and `run_quality` now runs only those two blocks (the still-placeholder `typecheck`/`build` blocks were dropped from the phase).

## How to use it

```
curl "http://localhost:8000/api/sessions/<session_id>/decisions/<event_id>/reexecution-set"
```

Returns 200 with `{session_id, event_id, reexecution_set}` where `reexecution_set` has exactly the keys `{nodes, edges, node_count, markdown}`. 404 when the session does not exist or the event id is not a captured decision.

## How to verify

```bash
.venv-ci/bin/pytest -q tests/test_reexecution.py   # fast feedback
.venv-ci/bin/pytest -q                             # full suite
.venv-ci/bin/ruff check .
```

Test coverage mirrors the acceptance criteria: a grounded decision citing a tool result (set = decision + cited result + upstream tool call + downstream, with the expected edges including `d1→t1` evidence with `source_class="tool_backed"`); an evidence-free decision (set = decision + downstream only, causal edges only); read-only vs required-rerun marking (cited/downstream `AGENT_TURN` → `read_only`, `TOOL_RESULT` → `required_rerun`); `None` for unknown *and* non-decision ids; determinism asserted both at the function level (two calls over `copy.deepcopy(events)` produce equal dicts) and over the wire (two identical GETs produce identical JSON bodies); plus the route happy path and both 404 paths (unknown decision, unknown session).
