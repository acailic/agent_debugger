# Semantic checkpoint restore (M2.3)

`POST /api/checkpoints/{id}/restore` used to mint a brand-new **empty** session carrying only config metadata. A restored run lost its history, its state, and any way to tell it apart from an original run. This change makes restore semantic: the new session now inherits the source session's event prefix, a provenance marker as its first event, and an initial checkpoint holding the source state — all written in one repository transaction.

## What the endpoint does now

Given a checkpoint anchored at event `a1`, restoring produces a new session containing:

1. **Copied prefix** — the source session's events up to and including `a1`, in original timestamp order. Event `id` is a global primary key, so every copied event gets a fresh UUID. An old→new id map remaps internal references:
   - `parent_id` → mapped id if the parent is in the prefix, `None` otherwise (dangling or later-event references are dropped);
   - `upstream_event_ids` and `evidence_event_ids` → in-prefix ids kept and remapped, out-of-prefix ids filtered out.
   Event type, name, timestamp, importance, data, and metadata are preserved. If the anchor id matches no event in the source session (e.g. a checkpoint created with an empty `event_id`), the prefix is empty and the session starts from the marker alone.
2. **Restore marker** — the first event of the new session. It reuses `EventType.AGENT_START` (storage strictly parses event types via `EventType(...)`, and a dedicated restore type would require SDK changes) and is identified by `name == "session_restored"` plus its `data`: `restore_token`, `source_checkpoint_id`, `source_session_id`, `copied_event_count`, `restored_at`. Its timestamp is `min(prefix timestamps) − 1µs` (or now, when the prefix is empty) so it reliably lists first — event listing orders by timestamp only.
3. **Initial checkpoint** — `sequence=1`, `event_id` = the mapped anchor id (or the marker's id for an empty prefix), `state` run through `serialize_checkpoint_state(validate_checkpoint_state(...))` exactly like `TraceContext.create_checkpoint` (plain dicts land under a `{framework, data}` wrapper; pre-wrapped states round-trip stably), `memory` deep-copied from the source, `importance` carried over, `timestamp` = restore time.

The response (`RestoreResponse`) gains three fields — `copied_event_count`, `new_checkpoint_id`, `restore_event_id` — with safe defaults; all existing fields (`checkpoint_id`, `original_session_id`, `new_session_id`, `restored_at`, `state`, `restore_token`, `replayed_events_count`, `drift_detected`) are unchanged. The response echoes the **raw** source state; only the stored checkpoint gets the wrapper.

No new storage repository methods and no DB migration were needed: the route composes existing calls (`get_event_tree`, `add_events_batch`, `add_event`, `create_session`, `create_checkpoint`, `commit`). Restores are deterministic — copied events keep original timestamps and only ids/tokens are minted fresh.

## Files

- `api/replay_routes.py` — three new module-level helpers (`_copy_prefix_events`, `_copy_event` with the reference-remapping rules, `_build_restore_marker`) and the rewritten `restore_checkpoint`. Note the remapping path: typed fields like `DecisionEvent.evidence_event_ids` are remapped inside the storage `data` dict (`to_storage_data()` merges them in), while `upstream_event_ids` lives in `metadata` on the storage side and goes through the keyword route.
- `api/schemas_core.py` — `RestoreResponse` extended by the three new fields. `api/schemas.py` re-exports it; nothing else changed.
- `tests/test_restore_semantics.py` — new suite (follows `test_reexecution.py` conventions: `_event` helper, `create_app` + httpx `ASGITransport`, unique session ids per test against a shared SQLite file). Covers prefix-copy correctness (structure, id freshness, remapped in-prefix refs, dropped out-of-prefix refs), checkpoint state hand-off (pre-wrapped and plain-dict), marker contents, audit coherence of a restored session (`GET /api/sessions/{new_id}/audit` resolves evidence cited inside the copied prefix, `verification_status == "verified"`), 404 for unknown checkpoints, and determinism (two restores from the same checkpoint normalize to equal traces).
- `tests/test_api_replay_routes_coverage.py` — one line in the `mock_repo` fixture: `repo.get_event_tree = AsyncMock(return_value=[])`, so the AsyncMock-driven restore tests iterate an empty prefix instead of raising on a `MagicMock`.
- `specs/c905da74_restore-semantics.md` — the implementation spec that drove this change: discovered constraints (strict `EventType` parsing, timestamp-only event ordering, state wrapping, audit engine's id lookup), the full change plan, and the verification block.

## How to use it

Same call as before:

```
POST /api/checkpoints/{checkpoint_id}/restore   {"session_id": "optional-explicit-id"}
```

Read back the restored session with `GET /api/sessions/{new_id}/traces` (marker first, then the copied prefix), `GET /api/sessions/{new_id}/checkpoints` (the initial checkpoint), `GET /api/checkpoints/{new_checkpoint_id}`, and `GET /api/sessions/{new_id}/audit` (claims resolve against remapped ids). Identify a restored run by the leading `session_restored` event or by `session.config.restored_from_checkpoint`.

## Verification

```bash
.venv-ci/bin/ruff check .
.venv-ci/bin/pytest -q tests/test_restore_semantics.py
.venv-ci/bin/pytest -q tests/test_api_replay_routes_coverage.py
.venv-ci/bin/pytest -q
```

## Out of scope (unchanged)

Frontend UI for restored sessions (no `RestoreResponse` frontend type exists to mirror), actually re-executing the agent from restored state, checkpoint creation, and the GET replay endpoint's slicing behavior.
