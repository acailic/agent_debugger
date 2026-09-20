# Plan — Minimal Re-execution Set (roadmap M2.1)

Implement the "minimal re-execution set" from the provenance survey note
(`docs/papers/from-agent-traces-to-trust-provenance-survey.md`, "Concrete
Opportunities" → roadmap `docs/ROADMAP.md` M2.1): for a suspect decision in a
session audit, compute the smallest sub-graph that would need to re-run to
confirm or invalidate that decision's claim, and expose it as a first-class
deterministic audit surface.

Pure computation over captured event fields — no LLM, no I/O, no randomness.
It does **not** execute anything; it names what *would* have to re-run.

## Scope

- New module `collector/audit/reexecution.py` — pure function of
  `(events, audit_report_dict, event_id)`, in the style of
  `collector/audit/failure_narrative.py`.
- New route in `api/audit_routes.py`:
  `GET /api/sessions/{session_id}/decisions/{event_id}/reexecution-set`,
  placed next to `get_decision_justification`.
- Response models in `api/schemas_analysis.py`.
- Export from `collector/audit/__init__.py`.
- Tests in `tests/test_reexecution.py` mirroring `tests/test_failure_narrative.py`
  conventions.

**Out of scope** (do not touch): frontend UI, actually re-executing tools,
trust score, claim verification statuses, behavior of the existing
justification / evidence-graph endpoints.

## 1. `collector/audit/reexecution.py` (new file)

Module docstring in the `failure_narrative.py` voice: deterministic
re-execution planning layer; every node resolves to a captured event id;
reference the roadmap M2.1 + provenance survey note.

### Public API

```python
def build_reexecution_set(
    events: list[TraceEvent], report: dict[str, Any], event_id: str
) -> dict[str, Any] | None:
```

- `report` is the dict produced by `SessionAuditEngine.audit(...)`.
- Look up the claim in `report["claims"]` by `event_id`. If no claim matches
  (unknown id, or the id belongs to a non-decision event) return `None` —
  the route maps that to 404, exactly like `justify_decision`.
- Returns the `reexecution_set` payload (below). Pure function: no I/O, no
  clock, no randomness.

### Node selection (role precedence: decision > evidence > upstream_tool_call > downstream)

1. **decision** — `event_id` itself. Always included.
2. **evidence** — every id in the claim's `evidence_refs`
   (`claim["evidence_refs"]`, preserved order, deduped) that resolves to an
   event in the trace (`id_lookup`). These are the resolved tool results /
   user inputs / retrieved facts whose outputs would have to be reproduced.
   Unresolved refs are skipped (nothing to re-run).
3. **upstream_tool_call** — for each evidence node, its direct upstream refs
   that are `EventType.TOOL_CALL` events: build the ordered parent-ref list
   `[event.parent_id] + list(upstream_event_ids)` (deduped, preserving
   order), include each ref that exists in the trace and has
   `event_type == TOOL_CALL`. Skip ids already assigned a role.
4. **downstream** — the decision's causal subtree: bounded BFS over the
   children index (same construction and same 2000-iteration bound the
   engine uses — write a local `_descendants()` helper ~12 lines mirroring
   `SessionAuditEngine._descendants_set`). Skip ids already assigned a role
   (an evidence ref that also sits downstream keeps its `evidence` role).

### Node payload

```python
{
    "event_id": str,
    "event_type": str,           # str(event.event_type)
    "label": str,                # event_label(event)
    "role": str,                 # "decision" | "evidence" | "upstream_tool_call" | "downstream"
    "mode": str,                 # "required_rerun" | "read_only"
    "why_included": str,         # one-line reason, see templates below
    "timestamp": str | None,     # same _iso(event) helper the engine uses
}
```

**Mode rule (deterministic):**
- `decision`, `upstream_tool_call` → `required_rerun`.
- `evidence` / `downstream` → `read_only` iff `event_type` is
  `AGENT_TURN` or `AGENT_START` (operator-supplied input: re-supplied
  verbatim, cannot be re-executed); otherwise `required_rerun` (tool
  results, retrieved facts, downstream tool calls/results, decisions, ...).

**`why_included` templates (one line each):**
- decision: `"the suspect decision under audit — re-run to confirm or invalidate its claim"`
- evidence, TOOL_RESULT: `"cited tool result — its output must be reproduced to re-verify the claim"`
- evidence, AGENT_TURN/AGENT_START: `"cited user input — re-supplied verbatim, not re-executed"`
- evidence, other: `"cited evidence — must be re-obtained to re-verify the claim"`
- upstream_tool_call: `f"tool call that produces the cited evidence {evidence_event_id} — must be re-invoked"`
- downstream, required_rerun: `"consumes the decision's output — re-runs when the decision is re-made"`
- downstream, read_only: `"operator input inside the decision's subtree — replayed verbatim"`

### Edges (reuse `build_evidence_graph` semantics)

- **evidence edges**: for each evidence node in the claim's ref order:
  `{source_id: decision_id, target_id: ref, edge_type: "evidence",
  source_class: _source_class_for(cited_event)}` — same
  `source_class` logic the evidence graph uses.
- **causal edges**: for each included node in trace order, walk its ordered
  parent refs (`parent_id` first, then `upstream_event_ids` in captured
  order); emit `{source_id: parent, target_id: node, edge_type: "causal",
  source_class: None}` whenever the parent is in the node set.
- Dedupe by `(source_id, target_id, edge_type, source_class)`.

**Determinism rules (hard requirements):** nodes sorted by trace position
(index in `events`); evidence edges follow `evidence_refs` order; causal
edges follow node trace order × captured parent-ref order. Never iterate a
Python `set` when emitting output order — build ordered lists. No caps on
subtree size (the full causal subtree is the set; the walk bound is only a
cycle guard).

### Return shape

```python
{
    "nodes": [...],       # trace order
    "edges": [...],       # evidence edges first, then causal (each in the deterministic order above)
    "node_count": len(nodes),
    "markdown": str,      # template below
}
```

### Markdown template (compact, deterministic)

```
# Minimal re-execution set — {event_id}

{node_count} event(s): {n_required} required-rerun, {n_read_only} read-only.

## Required re-runs
- `{event_id}` ({role}, {event_type}): {why_included}
...

## Read-only
- ... (or "None.")

## Edges
- `{source_id}` --{edge_type}--> `{target_id}` (or "None.")
```

Sections always emitted; node lines follow trace order.

### Imports within the package

```python
from .audit_engine import _build_children_index, _iso, _source_class_for
from ..intelligence.helpers import event_label
```

Reusing the private helpers (same package, stable, single source of truth)
guarantees edge semantics match `build_evidence_graph` exactly. No circular
import: `audit_engine` does not import `reexecution`.

`__all__ = ["build_reexecution_set"]`.

## 2. `collector/audit/__init__.py`

Add `from .reexecution import build_reexecution_set` and append
`"build_reexecution_set"` to `__all__` (mirrors how `build_failure_narrative`
is exported).

## 3. `api/schemas_analysis.py`

Insert after `DecisionJustificationResponse`, before
`EvidenceGraphNodeSchema`:

```python
class ReexecutionNodeSchema(BaseModel):
    """A node in a decision's minimal re-execution set."""
    event_id: str
    event_type: str
    label: str
    role: str  # decision | evidence | upstream_tool_call | downstream
    mode: str  # required_rerun | read_only
    why_included: str
    timestamp: str | None = None


class ReexecutionEdgeSchema(BaseModel):
    """An edge between nodes of a re-execution set (evidence or causal)."""
    source_id: str
    target_id: str
    edge_type: str  # evidence | causal
    source_class: str | None = None  # tool_backed | user_provided | other


class ReexecutionSetSchema(BaseModel):
    """Minimal re-execution set: what would have to re-run to re-verify a claim."""
    nodes: list[ReexecutionNodeSchema]
    edges: list[ReexecutionEdgeSchema]
    node_count: int
    markdown: str


class ReexecutionSetResponse(BaseModel):
    """Response schema for the per-decision re-execution set endpoint."""
    session_id: str
    event_id: str
    reexecution_set: ReexecutionSetSchema
```

## 4. `api/audit_routes.py`

- Extend imports: add `ReexecutionSetResponse` to the
  `api.schemas_analysis` import block (alphabetical: after
  `PortfolioAuditResponse`, before `SessionAuditResponse`); change
  `from collector.audit import SessionAuditEngine` to
  `from collector.audit import SessionAuditEngine, build_reexecution_set`.
- Add the route directly after `get_decision_justification`, mirroring its
  error/commit/rollback structure exactly:

```python
@router.get(
    "/api/sessions/{session_id}/decisions/{event_id}/reexecution-set",
    response_model=ReexecutionSetResponse,
)
async def get_decision_reexecution_set(
    session_id: str,
    event_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> ReexecutionSetResponse:
    """Return the minimal re-execution set for a suspect decision.

    The smallest sub-graph that would need to re-run to confirm or
    invalidate the decision's claim: the decision, its cited evidence, the
    tool calls producing that evidence, and the downstream subtree that
    consumed the decision's output — each marked read-only vs
    required-rerun. Deterministic; nothing is executed.
    """
    session = await require_session(repo, session_id)
    try:
        events, _checkpoints, analysis, _ = await analyze_session(repo, session_id)
        report = _audit_engine.audit(
            events,
            session=_session_dict(session),
            failure_explanations=analysis.get("failure_explanations", []),
        )
        reexecution_set = build_reexecution_set(events, report, event_id)
        if reexecution_set is None:
            raise NotFoundError(f"Decision {event_id} not found in session {session_id}")
        await repo.commit()
    except Exception:
        await repo.rollback()
        raise
    record_event("decision_reexecution_set_viewed", session_id=session_id)
    return ReexecutionSetResponse(
        session_id=session_id, event_id=event_id, reexecution_set=reexecution_set
    )
```

404s come from `require_session` (missing session) and the `None` →
`NotFoundError` path (missing/non-decision event id) — same behavior as the
justification route.

## 5. `tests/test_reexecution.py` (new file)

Mirror `tests/test_failure_narrative.py` conventions: module docstring, the
`_event` / `_decision` helpers (copy the helpers verbatim, session id
`"reexec-session"`), imports (`copy`, `datetime/timezone`, `pytest`, httpx
`ASGITransport`/`AsyncClient`, SDK `EventType/Session/SessionStatus/TraceEvent`,
`create_app`, `SessionAuditEngine`, `TraceRepository`,
`build_reexecution_set` from `collector.audit.reexecution`).

Shared fixture pattern: a grounded session
`c1 (TOOL_CALL) → t1 (TOOL_RESULT, parent c1)`, `d1 (DECISION citing t1)`,
`f1 (TOOL_RESULT, parent d1)`; report via `SessionAuditEngine().audit(events)`.

Unit tests:
1. `test_reexecution_set_grounded_decision_cites_tool_result` — node id set
   is `{d1, t1, c1, f1}` with roles decision / evidence / upstream_tool_call
   / downstream; `node_count == 4`; every node has a non-empty
   `why_included`; all four modes are `required_rerun`; edges include
   `(d1→t1, evidence, source_class="tool_backed")`, `(c1→t1, causal)`,
   `(d1→f1, causal)`; `markdown` contains the header and all four event ids.
2. `test_reexecution_set_upstream_tool_call_omitted_when_evidence_has_no_call`
   — decision citing `t1` with no TOOL_CALL parent → no upstream node
   (guards the role walk against inventing nodes).
3. `test_reexecution_set_evidence_free_decision_downstream_only` — decision
   with no evidence refs + one downstream child → node set is
   `{d1, downstream}`, `node_count == 2`, edges are causal only (no
   `evidence` edges).
4. `test_reexecution_set_marks_read_only_vs_required_rerun_downstream` —
   decision with downstream `TOOL_RESULT` (→ `required_rerun`) and a
   downstream `AGENT_TURN` carrying `content` (→ `read_only`); also cite an
   `AGENT_TURN` as evidence → evidence node is `read_only` while the cited
   `TOOL_RESULT` stays `required_rerun`.
5. `test_reexecution_set_unknown_or_non_decision_event_returns_none` —
   `build_reexecution_set(events, report, "nope")` is `None`; also `None`
   for the id of a non-decision event (`t1`).
6. `test_reexecution_set_is_deterministic` — two calls over
   `copy.deepcopy(events)` (fresh audit + builder each time) produce equal
   dicts.

Route tests (create_app + `ASGITransport`, seed via
`app_context.require_session_maker()()` + `TraceRepository`, inline `Session`
construction like the failure-narrative route test; unique session ids
`"reexec-route-session"`, `"reexec-route-404-session"`):
7. `test_reexecution_route_returns_set` — seed tool result + decision citing
   it + a downstream child event; `GET
   /api/sessions/reexec-route-session/decisions/{eid}/reexecution-set` →
   200; body has `session_id`, `event_id`, and `reexecution_set` with
   exactly the keys `{nodes, edges, node_count, markdown}`; node ids include
   the decision and the cited tool result; `node_count == len(nodes)`. GET
   the same URL twice and assert `resp1.json() == resp2.json()` (payload
   determinism over the wire).
8. `test_reexecution_route_unknown_decision_returns_404` — existing session,
   `event_id="nope"` → 404.
9. `test_reexecution_route_unknown_session_returns_404` — GET against a
   session id that was never created → 404.

## Verification (both must pass before done)

```bash
.venv-ci/bin/ruff check .
.venv-ci/bin/pytest -q tests/test_reexecution.py   # fast feedback first
.venv-ci/bin/pytest -q                             # full suite
```

Style guardrails: 120-char lines, files end with a newline, imports sorted
(ruff `I` rule), Python 3.10+ syntax via `from __future__ import annotations`.
Run `git status --short` first and leave unrelated worktree changes alone.
No frontend build needed (no frontend files touched). If a genuinely
non-obvious pitfall is discovered, record it in `DISCOVERIES.md`.

## Notes for the builder

- The determinism test must not iterate sets when constructing expected
  order; assert on sorted/set-comparisons for membership and on the exact
  `node_count`.
- `_build_children_index` treats `evidence_event_ids` as parent refs too —
  that is intended (a decision citing a fact depends on it); the subtree
  walk from the decision is unaffected except when downstream events cite
  the decision itself, which is a legitimate dependency.
- Keep the module free of any engine construction — it receives the report
  dict, it never calls `SessionAuditEngine` itself (the route does).
