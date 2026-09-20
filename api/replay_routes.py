"""Replay-oriented API routes."""

from __future__ import annotations

import copy
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from agent_debugger_sdk.checkpoints import serialize_checkpoint_state, validate_checkpoint_state
from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent
from api.analytics_db import record_event
from api.dependencies import get_repository
from api.exceptions import NotFoundError
from api.schemas import (
    CheckpointSchema,
    CollapsedSegmentSchema,
    ReplayResponse,
    RestoreRequest,
    RestoreResponse,
)
from api.services import load_session_artifacts, normalize_checkpoint, require_session
from collector.replay import build_replay
from collector.replay_collapse import identify_low_value_segments
from storage import TraceRepository

router = APIRouter(tags=["replay"])


def _split_csv_param(value: str | None) -> set[str]:
    return {item.strip() for item in (value or "").split(",") if item.strip()}


@router.get("/api/sessions/{session_id}/replay", response_model=ReplayResponse)
async def replay_session(
    session_id: str,
    mode: str = Query(default="full", pattern="^(full|focus|failure|highlights)$"),
    focus_event_id: str | None = Query(default=None),
    breakpoint_event_types: str | None = Query(default=None),
    breakpoint_tool_names: str | None = Query(default=None),
    breakpoint_confidence_below: float | None = Query(default=None, ge=0.0, le=1.0),
    breakpoint_safety_outcomes: str | None = Query(default=None),
    stop_at_breakpoint: bool = Query(default=False),
    collapse_threshold: float = Query(default=0.35, ge=0.0, le=1.0),
    repo: TraceRepository = Depends(get_repository),
) -> ReplayResponse:
    await require_session(repo, session_id)
    events, checkpoints = await load_session_artifacts(repo, session_id)

    # FastAPI resolves Query defaults in HTTP calls but not in direct/unit-test calls.
    # Extract the default value when the raw Query object is passed through.
    # Check for the Query class by examining if the value has a 'default' attribute
    # and is not already a primitive type.
    from fastapi import params

    if isinstance(collapse_threshold, params.Query):
        collapse_threshold = float(collapse_threshold.default)
    if isinstance(stop_at_breakpoint, params.Query):
        stop_at_breakpoint = bool(stop_at_breakpoint.default)

    # Record analytics event (fire-and-forget)
    record_event("replay_started", session_id=session_id, properties={"mode": mode})

    if not events:
        return ReplayResponse(
            session_id=session_id,
            mode=mode,
            focus_event_id=focus_event_id,
            start_index=0,
            events=[],
            checkpoints=[],
            nearest_checkpoint=None,
            breakpoints=[],
            failure_event_ids=[],
            collapsed_segments=[],
            highlight_indices=[],
            stopped_at_breakpoint=False,
            stopped_at_index=None,
        )

    replay_data = build_replay(
        events,
        checkpoints,
        mode=mode,
        focus_event_id=focus_event_id,
        breakpoint_event_types=_split_csv_param(breakpoint_event_types),
        breakpoint_tool_names=_split_csv_param(breakpoint_tool_names),
        breakpoint_confidence_below=breakpoint_confidence_below,
        breakpoint_safety_outcomes=_split_csv_param(breakpoint_safety_outcomes),
    )

    # Handle segment collapsing for highlights mode
    collapsed_segments: list[CollapsedSegmentSchema] = []
    if mode == "highlights":
        segments = identify_low_value_segments(events, threshold=collapse_threshold)
        collapsed_segments = [CollapsedSegmentSchema(**asdict(s)) for s in segments]
        # Record analytics event for highlights mode (fire-and-forget)
        record_event("replay_highlights_used", session_id=session_id)

    # Compute highlight indices (indices of high-importance events)
    highlight_indices: list[int] = [
        i for i, event in enumerate(replay_data["events"]) if (event.get("importance") or 0) >= collapse_threshold
    ]

    # Handle stop_at_breakpoint
    stopped_at_breakpoint = False
    stopped_at_index: int | None = None
    if stop_at_breakpoint and replay_data["breakpoints"]:
        stopped_at_breakpoint = True
        # Build O(1) event_id -> index map for efficient breakpoint lookup
        event_id_to_index = {event.get("id"): i for i, event in enumerate(replay_data["events"])}
        for breakpoint_event in replay_data["breakpoints"]:
            stopped_at_index = event_id_to_index.get(breakpoint_event.get("id"))
            if stopped_at_index is not None:
                break

    return ReplayResponse(
        session_id=session_id,
        mode=replay_data["mode"],
        focus_event_id=replay_data["focus_event_id"],
        start_index=replay_data["start_index"],
        events=replay_data["events"],
        checkpoints=replay_data["checkpoints"],
        nearest_checkpoint=replay_data["nearest_checkpoint"],
        breakpoints=replay_data["breakpoints"],
        failure_event_ids=replay_data["failure_event_ids"],
        collapsed_segments=collapsed_segments,
        highlight_indices=highlight_indices,
        stopped_at_breakpoint=stopped_at_breakpoint,
        stopped_at_index=stopped_at_index,
    )


@router.get("/api/checkpoints/{checkpoint_id}", response_model=CheckpointSchema)
async def get_checkpoint(
    checkpoint_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> CheckpointSchema:
    """Get a single checkpoint by ID."""
    checkpoint = await repo.get_checkpoint(checkpoint_id)
    if checkpoint is None:
        raise NotFoundError(f"Checkpoint {checkpoint_id} not found")

    return CheckpointSchema(
        **normalize_checkpoint(checkpoint).model_dump(),
    )


def _copy_event(event: TraceEvent, new_session_id: str, id_map: dict[str, str]) -> TraceEvent:
    """Copy one event into a new session with a fresh id and remapped references.

    Typed event fields (e.g. ``DecisionEvent.evidence_event_ids``) are merged
    into the storage payload by ``to_storage_data()`` and split back out by
    ``from_data``, so remapping them inside the payload keeps typed structure
    intact. ``upstream_event_ids`` lives in ``metadata`` on the storage side, so
    it is remapped via the keyword route instead.

    References pointing outside the copied prefix are dropped: ``parent_id``
    becomes ``None`` and out-of-prefix ids are filtered from the id lists.
    """
    data = event.to_storage_data()
    if isinstance(data.get("evidence_event_ids"), list):
        data["evidence_event_ids"] = [id_map[e] for e in data["evidence_event_ids"] if e in id_map]
    return TraceEvent.from_data(
        event.event_type,
        {
            "id": id_map[event.id],
            "session_id": new_session_id,
            "parent_id": id_map.get(event.parent_id) if event.parent_id else None,
            "timestamp": event.timestamp,
            "name": event.name,
            "metadata": {
                key: value for key, value in event.metadata.items() if key != "upstream_event_ids"
            },
            "importance": event.importance,
            "upstream_event_ids": [id_map[e] for e in event.upstream_event_ids if e in id_map],
        },
        data,
    )


def _copy_prefix_events(
    source_events: list[TraceEvent], anchor_event_id: str, new_session_id: str
) -> tuple[list[TraceEvent], dict[str, str]]:
    """Copy the events up to and including the anchor event into a new session.

    Event ids are a global primary key, so every copied event gets a new id;
    the returned old-to-new id map remaps in-prefix ``parent_id`` /
    ``upstream_event_ids`` / ``evidence_event_ids`` references. If the anchor
    id does not match any event of the source session (e.g. a checkpoint
    created with an empty ``event_id``), the prefix is empty and the restored
    session starts from the restore marker alone.
    """
    anchor_index = next((i for i, event in enumerate(source_events) if event.id == anchor_event_id), None)
    prefix = source_events[: anchor_index + 1] if anchor_index is not None else []
    id_map = {event.id: str(uuid.uuid4()) for event in prefix}
    return [_copy_event(event, new_session_id, id_map) for event in prefix], id_map


def _build_restore_marker(
    new_session_id: str,
    checkpoint: Checkpoint,
    restore_token: str,
    copied_count: int,
    prefix: list[TraceEvent],
    restored_at: str,
) -> TraceEvent:
    """Build the first event of a restored session marking its provenance.

    The marker reuses ``EventType.AGENT_START`` (storage strictly parses event
    types and a dedicated restore type would require SDK changes) and is
    identifiable by ``name == "session_restored"`` plus its structured data.
    Its timestamp is strictly earlier than every copied event so it reliably
    lists first (event listing orders by timestamp only).
    """
    timestamp = (
        min(event.timestamp for event in prefix) - timedelta(microseconds=1)
        if prefix
        else datetime.now(timezone.utc)
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
            "restored_at": restored_at,
        },
    )


@router.post("/api/checkpoints/{checkpoint_id}/restore", response_model=RestoreResponse)
async def restore_checkpoint(
    checkpoint_id: str,
    request: RestoreRequest,
    repo: TraceRepository = Depends(get_repository),
) -> RestoreResponse:
    """Restore execution from a checkpoint by creating a new session.

    The new session carries the source session's history up to and including
    the checkpoint's anchor event (copied with fresh ids and remapped internal
    references), a leading restore-marker event, and an initial checkpoint
    holding the source checkpoint's state and memory — so the restored run
    keeps its auditability and can be continued from a known state.
    """
    from agent_debugger_sdk.core.events import Session

    checkpoint = await repo.get_checkpoint(checkpoint_id)
    if checkpoint is None:
        raise NotFoundError(f"Checkpoint {checkpoint_id} not found")

    source_events = await repo.get_event_tree(checkpoint.session_id)

    new_session_id = request.session_id or str(uuid.uuid4())
    restore_token = str(uuid.uuid4())
    restored_at_dt = datetime.now(timezone.utc)
    restored_at = restored_at_dt.isoformat()

    copied_events, id_map = _copy_prefix_events(source_events, checkpoint.event_id, new_session_id)
    marker = _build_restore_marker(
        new_session_id, checkpoint, restore_token, len(copied_events), copied_events, restored_at
    )

    new_session = Session(
        id=new_session_id,
        agent_name=request.label or f"restored from {checkpoint_id[:8]}",
        framework=checkpoint.state.get("framework", "custom"),
        config={
            "restored_from_checkpoint": checkpoint_id,
            "original_session_id": checkpoint.session_id,
            "restore_token": restore_token,
        },
    )
    await repo.create_session(new_session)
    if copied_events:
        await repo.add_events_batch(copied_events)
    await repo.add_event(marker)

    wrapped_state = serialize_checkpoint_state(validate_checkpoint_state(checkpoint.state or {}))
    initial_checkpoint = Checkpoint(
        id=str(uuid.uuid4()),
        session_id=new_session_id,
        event_id=id_map.get(checkpoint.event_id, marker.id),
        sequence=1,
        state=wrapped_state,
        memory=copy.deepcopy(checkpoint.memory or {}),
        timestamp=restored_at_dt,
        importance=checkpoint.importance,
    )
    await repo.create_checkpoint(initial_checkpoint)
    await repo.commit()

    return RestoreResponse(
        checkpoint_id=checkpoint_id,
        original_session_id=checkpoint.session_id,
        new_session_id=new_session_id,
        restored_at=restored_at,
        state=checkpoint.state,
        restore_token=restore_token,
        copied_event_count=len(copied_events),
        new_checkpoint_id=initial_checkpoint.id,
        restore_event_id=marker.id,
    )
