# Plan — M2.3: Semantic restore for `POST /api/checkpoints/{id}/restore`

## Problem

Today the restore endpoint (`api/replay_routes.py::restore_checkpoint`) only mints an
**empty** new session carrying config metadata (`restored_from_checkpoint`,
`original_session_id`, `restore_token`). The restored run loses its history (events),
its state (no checkpoint is created in the new session), and its auditability (no marker
distinguishing a restored run from an original).

## Goal (done criteria)

Restoring a checkpoint whose anchor event has N events before it yields a new session that
contains:

1. Those N prefix events **copied with new ids** (event `id` is a global PK in
   `storage/models.py`) while preserving structure, with `parent_id`,
   `upstream_event_ids`, and `evidence_event_ids` references **remapped** through an
   old→new id map; references to events outside the copied prefix are **dropped**
   (`parent_id` becomes `None`, ids are filtered out of the lists).
2. A **leading restore marker event** — the first event of the new session — with a clear
   name and data carrying `restore_token`, source checkpoint id, source session id,
   `copied_event_count`.
3. An **initial checkpoint** carrying the source checkpoint's state (wrapped the same way
   the SDK serializes checkpoint state — plain dicts land under a `{framework, data}`
   wrapper via `agent_debugger_sdk/checkpoints/validation.py`) and its memory.

`GET /api/sessions/{new_id}/audit` must succeed on the restored session and resolve
evidence cited inside the copied prefix. The restore response reports `copied_event_count`,
the new checkpoint id, and the restore marker event id, keeping all existing fields.

## Key facts discovered (read these before coding)

- `EventType` has no RESTORE member, and `storage/converters.orm_to_event` does
  `EventType(db_event.event_type)` — **an unregistered event_type string would crash on
  read-back**. The prompt's "Where" list does not include SDK changes, so the marker
  **reuses `EventType.AGENT_START`** with `name="session_restored"` and a structured
  `data` payload. It is identifiable by name + `data.restore_token` (and by
  `session.config.restored_from_checkpoint`, which already exists).
- Event listing (`storage/repositories/event_repo.py`) orders by **timestamp only** —
  no secondary key. For the marker to reliably list first, its timestamp must be
  strictly earlier than every copied event: use `min(prefix timestamps) - 1µs`
  (or `datetime.now(utc)` when the prefix is empty). Copied events keep their original
  timestamps, which also makes repeated restores deterministic.
- Typed event fields (e.g. `DecisionEvent.evidence_event_ids`) live as dataclass fields,
  NOT in `.data`; `TraceEvent.to_storage_data()` merges them into the storage `data`
  dict, and `TraceEvent.from_data(event_type, base_kwargs, data)` splits them back out.
  `orm_to_event` uses exactly this round-trip — copy events through the same path.
- `upstream_event_ids` is persisted inside `event_metadata` (see
  `storage/converters.event_to_orm`), never in `.data`.
- Checkpoint state wrapping: `validate_checkpoint_state(dict) → serialize_checkpoint_state`
  (from `agent_debugger_sdk.checkpoints`) is what `TraceContext.create_checkpoint` uses.
  Already-serialized states (`{"framework": ..., "data": ...}`, `"messages"` for langchain)
  round-trip stably; plain dicts like `{"stage": 2}` get wrapped into
  `{"framework": "custom", "label": "", "created_at": <iso>, "data": {"stage": 2}}`.
  This is exactly the behavior the prompt asks for.
- The audit engine (`collector/audit/audit_engine.py`) builds claims from DECISION events,
  resolving `evidence_event_ids` against the session's own event ids
  (`resolved_evidence_ids = [eid for eid in evidence_event_ids if eid in id_lookup]`).
  Remapped ids therefore resolve; a decision citing a copied TOOL_RESULT gets
  `verification_status == "verified"` (tool-backed).
- Existing repo API already covers everything needed:
  `get_event_tree(session_id)` (all events, timestamp order), `add_events_batch(events)`
  (also increments session error counters for copied ERROR events — desirable),
  `add_event`, `create_session`, `create_checkpoint`, `commit`.
  **No new repository methods are required.**
- `tests/test_api_replay_routes_coverage.py` drives the restore route with an
  `AsyncMock` repo. `mock_repo.get_event_tree` must return `[]` by default or iteration
  over a `MagicMock` will raise. The route must use **locally constructed** ids
  (marker/checkpoint), not values read back from repo return values, to stay mock-safe.
- `.venv-ci/` exists (ruff 0.15.7). Prompt-mandated validation:
  `.venv-ci/bin/pytest -q` and `.venv-ci/bin/ruff check .`.
- Frontend has **no** `RestoreResponse` type (checked `frontend/src/types/index.ts` and
  `client.ts`) — no frontend change needed for this contract addition.

## Changes

### 1. `api/schemas_core.py` — extend `RestoreResponse`

Add three fields (defaults keep any direct constructions working; the route always sets
them). Existing fields untouched:

```python
class RestoreResponse(BaseModel):
    checkpoint_id: str
    original_session_id: str
    new_session_id: str
    restored_at: str
    state: dict[str, Any]
    restore_token: str
    replayed_events_count: int | None = None      # unchanged, stays None
    drift_detected: bool | None = None            # unchanged, stays None
    copied_event_count: int = 0                   # NEW
    new_checkpoint_id: str = ""                   # NEW
    restore_event_id: str = ""                    # NEW
```

(`api/schemas.py` re-exports from `schemas_core`; no change there.)

### 2. `api/replay_routes.py` — semantic restore

Add module-level private helpers plus rewrite `restore_checkpoint`. New imports:
`timedelta`, `copy`, `TraceEvent`, `EventType`, `Checkpoint` from
`agent_debugger_sdk.core.events`, and `validate_checkpoint_state` /
`serialize_checkpoint_state` from `agent_debugger_sdk.checkpoints`.

**Helper — prefix copy (pure, no I/O):**

```python
def _copy_prefix_events(
    source_events: list[TraceEvent], anchor_event_id: str, new_session_id: str
) -> tuple[list[TraceEvent], dict[str, str]]:
    anchor_index = next((i for i, e in enumerate(source_events) if e.id == anchor_event_id), None)
    prefix = source_events[: anchor_index + 1] if anchor_index is not None else []
    id_map = {e.id: str(uuid.uuid4()) for e in prefix}
    return [_copy_event(e, new_session_id, id_map) for e in prefix], id_map
```

Anchor not found among the session's events (e.g. checkpoint created with
`event_id=""` outside a `set_parent` scope) ⇒ empty prefix; the new checkpoint then
anchors on the marker event. Document this in the helper docstring.

**Helper — single event copy with reference remapping:**

```python
def _copy_event(event: TraceEvent, new_session_id: str, id_map: dict[str, str]) -> TraceEvent:
    data = event.to_storage_data()   # merges typed fields (e.g. evidence_event_ids) into data
    if isinstance(data.get("evidence_event_ids"), list):
        data["evidence_event_ids"] = [id_map[e] for e in data["evidence_event_ids"] if e in id_map]
    metadata = {k: v for k, v in event.metadata.items() if k != "upstream_event_ids"}
    return TraceEvent.from_data(
        event.event_type,
        {
            "id": id_map[event.id],
            "session_id": new_session_id,
            "parent_id": id_map.get(event.parent_id) if event.parent_id else None,
            "timestamp": event.timestamp,      # preserved → stable order + determinism
            "name": event.name,
            "metadata": metadata,
            "importance": event.importance,
            "upstream_event_ids": [id_map[e] for e in event.upstream_event_ids if e in id_map],
        },
        data,
    )
```

Remapping rules (test these exactly):
- `parent_id` referencing an in-prefix event → mapped new id; referencing anything else
  (later event, dangling id) → `None`.
- `upstream_event_ids` / `evidence_event_ids`: keep+remap in-prefix ids, drop the rest.
- Everything else (event_type, name, timestamp, importance, data, metadata) preserved.

**Helper — restore marker:**

```python
def _build_restore_marker(new_session_id, checkpoint, restore_token, copied_count, prefix) -> TraceEvent:
    timestamp = (
        min(e.timestamp for e in prefix) - timedelta(microseconds=1) if prefix else datetime.now(timezone.utc)
    )
    return TraceEvent(
        id=str(uuid.uuid4()),
        session_id=new_session_id,
        parent_id=None,
        event_type=EventType.AGENT_START,
        timestamp=timestamp,
        name="session_restored",
        importance=1.0,
        data={
            "restore_token": restore_token,
            "source_checkpoint_id": checkpoint.id,
            "source_session_id": checkpoint.session_id,
            "copied_event_count": copied_count,
            "restored_at": <iso string>,
        },
    )
```

**Rewritten endpoint** (keep 404 for unknown checkpoint; keep session construction and
config metadata exactly as today; single transaction, one commit at the end):

1. `checkpoint = await repo.get_checkpoint(...)`; `None` → `NotFoundError` (unchanged).
2. `source_events = await repo.get_event_tree(checkpoint.session_id)`.
3. Compute `new_session_id`, `restore_token`, `restored_at_dt`/`restored_at` (unchanged logic).
4. `copied, id_map = _copy_prefix_events(source_events, checkpoint.event_id, new_session_id)`.
5. `marker = _build_restore_marker(...)`.
6. `await repo.create_session(new_session)` (unchanged `Session(...)` construction).
7. `if copied: await repo.add_events_batch(copied)`.
8. `await repo.add_event(marker)`.
9. Wrap state:
   `wrapped = serialize_checkpoint_state(validate_checkpoint_state(checkpoint.state or {}))`.
10. Create the initial checkpoint:
    ```python
    initial = Checkpoint(
        id=str(uuid.uuid4()),
        session_id=new_session_id,
        event_id=id_map.get(checkpoint.event_id, marker.id),  # mapped anchor; marker if empty prefix
        sequence=1,
        state=wrapped,
        memory=copy.deepcopy(checkpoint.memory or {}),
        timestamp=restored_at_dt,
        importance=checkpoint.importance,
    )
    await repo.create_checkpoint(initial)
    ```
11. `await repo.commit()`.
12. Return `RestoreResponse(... existing fields ..., state=checkpoint.state,`
    `copied_event_count=len(copied), new_checkpoint_id=initial.id, restore_event_id=marker.id)`
    — use the locally constructed `initial.id` / `marker.id`, not repo return values.

### 3. `tests/test_restore_semantics.py` — new file

Follow `tests/test_reexecution.py` conventions exactly: module docstring; `_event()`
helper (id, event_type, session_id, parent_id, upstream_event_ids, fixed tz-aware
timestamp, `**data`); route tests as `@pytest.mark.asyncio async def ...(shared_app)`
using `app = create_app()`, `ASGITransport`, `AsyncClient(base_url="http://test")`;
seed data through `app_context.require_session_maker()()` + `TraceRepository` +
`db_session.commit()`; **unique session ids per test** (shared per-worker SQLite file).

Seed fixture (one async seeding helper used by most tests): source session with, in
timestamp order — `u1` (AGENT_TURN), `c1` (TOOL_CALL), `t1` (TOOL_RESULT,
`parent_id="c1"`, plus `parent_id` to a nonexistent `"ghost"` on one event to exercise
the dropped-parent rule — e.g. give `u1` `parent_id="ghost"`), `d1` (DECISION,
`evidence_event_ids=["t1", "outside-evidence"]`, `upstream_event_ids=["c1", "outside-upstream"]`),
anchor `a1` (TOOL_RESULT), then post-anchor `f1` (TOOL_RESULT, `parent_id="d1"`).
Checkpoint `cp1` anchored at `a1` with SDK-shaped state
(`serialize_checkpoint_state(validate_checkpoint_state({"framework": "custom", ...}))`
or simply `{"framework": "custom", "data": {"stage": 2}}`) and
`memory={"last_table": "revenue_daily"}`.

Tests (fetch restored artifacts via `GET /api/sessions/{new_id}/trace` —
`TraceEventSchema` is the flat-union schema, so `evidence_event_ids`/`upstream_event_ids`
appear as top-level optional fields — and `GET /api/sessions/{new_id}/checkpoints`;
deep assertions may alternatively read through a fresh repo session):

1. **Prefix copy correctness** — POST restore; assert response `copied_event_count == 4`
   (`u1, c1, t1, d1, a1` — count whatever the seed yields, post-anchor `f1` excluded);
   trace events: `events[0]` is the marker; the next N events match the source prefix in
   order (event_type, name, data minus remapped id lists, timestamp), all have
   `session_id == new_id`, all ids differ from source ids and are unique; `t1'` has
   `parent_id == c1'.id`; `u1'` has `parent_id is None` (ghost dropped); `d1'` has
   `evidence_event_ids == [t1'.id]` and `upstream_event_ids == [c1'.id]`
   (outside refs dropped).
2. **Checkpoint state hand-off** — new session has exactly one checkpoint;
   `state["framework"] == "custom"` and `state["data"] == {"stage": 2}`;
   `memory == {"last_table": "revenue_daily"}`; `event_id` == mapped anchor id;
   `sequence == 1`; `GET /api/checkpoints/{response.new_checkpoint_id}` returns it.
3. **Plain-dict state gets the SDK wrapper** — seed a second checkpoint with raw
   `state={"stage": 7}` (no framework key); restore it; new checkpoint state is
   `{"framework": "custom", "label": "", "created_at": <str>, "data": {"stage": 7}}`.
4. **Restore marker contents** — first event: `event_type == "agent_start"`,
   `name == "session_restored"`, `data["restore_token"] == response.restore_token`,
   `data["source_checkpoint_id"] == cp1.id`,
   `data["source_session_id"] == source_session_id`,
   `data["copied_event_count"] == N`; response `restore_event_id == marker.id`.
5. **Audit coherence** — `GET /api/sessions/{new_id}/audit` → 200; find the copied
   decision's claim in `audit["claims"]`; assert its `evidence_refs` all resolve to ids
   present in the new session's events and `verification_status == "verified"`
   (tool-backed evidence inside the prefix).
6. **404** — POST `/api/checkpoints/{uuid4()}/restore` → 404 (unknown checkpoint).
7. **Determinism** — restore the same checkpoint twice (two explicit `session_id`s);
   normalize each new session's event list — drop the marker's volatile data keys
   (`restore_token`, `restored_at`), map every event id to its list position, rewrite
   `parent_id`/`upstream_event_ids`/`evidence_event_ids` as positions — the normalized
   lists are equal; `copied_event_count` equal. (Checkpoint `created_at` differs between
   plain-dict restores; compare state `framework`+`data`, not raw dicts, in this test —
   or use the pre-wrapped seed.)
8. **Backwards-compat response fields** — the response still carries `checkpoint_id`,
   `original_session_id`, `new_session_id`, `restored_at`, `state` (raw source state),
   `restore_token` (fold into test 1 or 4).

### 4. `tests/test_api_replay_routes_coverage.py` — keep mocked tests green

In the `mock_repo` fixture add:

```python
repo.get_event_tree = AsyncMock(return_value=[])
```

so the restore route's prefix copy iterates an empty list. The three existing
`TestRestoreCheckpointEndpoint` tests then keep passing (restore with empty prefix:
0 copied events, marker + checkpoint still created; `state={"agent_state": "active"}`
wraps to the custom framework). Optionally extend one of them to assert the new
response fields are present — not required.

## Explicitly out of scope

- Frontend UI for restored sessions (no frontend type exists for RestoreResponse —
  nothing to mirror).
- Actually re-executing the agent from restored state; restore hooks; drift tracking.
- Changes to checkpoint creation (`TraceContext.create_checkpoint`) or to the GET replay
  endpoint's slicing behavior.
- New `EventType` enum member (rejected: would require SDK changes outside the stated
  scope and ripple through `orm_to_event`'s strict `EventType(...)` parse, registry,
  and frontend unions; name+data make the marker first-class enough).
- New storage repository methods (existing API suffices) and any DB migration
  (no schema change — event ids are client-generated UUIDs).

## Verification (must pass before done)

```bash
.venv-ci/bin/ruff check .
.venv-ci/bin/pytest -q tests/test_restore_semantics.py -q          # new coverage
.venv-ci/bin/pytest -q tests/test_api_replay_routes_coverage.py -q # mocked route still green
.venv-ci/bin/pytest -q tests/e2e -q                                # S8 restore e2e unaffected
.venv-ci/bin/pytest -q                                             # full suite
```

Also sanity-check the OpenAPI contract still renders (response model change only adds
fields): `.venv-ci/bin/python3 -c "from api.main import create_app; print(create_app().openapi()['paths']['/api/checkpoints/{checkpoint_id}/restore']['post']['responses']['200']['content']['application/json'])"`
— optional; the route tests already exercise the schema.
