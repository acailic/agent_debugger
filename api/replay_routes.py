"""Replay-oriented API routes."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from api.analytics_db import record_event
from api.dependencies import get_repository
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

    # Unwrap Query default (FastAPI resolves this in HTTP calls but not in direct/unit-test calls)
    if hasattr(collapse_threshold, "default"):
        collapse_threshold = collapse_threshold.default

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
        breakpoint_event_types={item for item in (breakpoint_event_types or "").split(",") if item},
        breakpoint_tool_names={item for item in (breakpoint_tool_names or "").split(",") if item},
        breakpoint_confidence_below=breakpoint_confidence_below,
        breakpoint_safety_outcomes={item for item in (breakpoint_safety_outcomes or "").split(",") if item},
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
        first_breakpoint_id = replay_data["breakpoints"][0].get("id")
        stopped_at_index = event_id_to_index.get(first_breakpoint_id)

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
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    return CheckpointSchema(
        **normalize_checkpoint(checkpoint).model_dump(),
    )


@router.post("/api/checkpoints/{checkpoint_id}/restore", response_model=RestoreResponse)
async def restore_checkpoint(
    checkpoint_id: str,
    request: RestoreRequest,
    repo: TraceRepository = Depends(get_repository),
) -> RestoreResponse:
    """Restore execution from a checkpoint by creating a new session."""
    checkpoint = await repo.get_checkpoint(checkpoint_id)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    from agent_debugger_sdk.core.events import Session

    new_session_id = request.session_id or str(uuid.uuid4())
    restore_token = str(uuid.uuid4())
    restored_at = datetime.now(timezone.utc).isoformat()

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
    await repo.commit()

    return RestoreResponse(
        checkpoint_id=checkpoint_id,
        original_session_id=checkpoint.session_id,
        new_session_id=new_session_id,
        restored_at=restored_at,
        state=checkpoint.state,
        restore_token=restore_token,
    )
