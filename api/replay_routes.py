"""Replay-oriented API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_repository
from api.schemas import ReplayResponse
from api.services import load_session_artifacts, require_session
from collector.replay import build_replay
from storage import TraceRepository

router = APIRouter(tags=["replay"])


@router.get("/api/sessions/{session_id}/replay", response_model=ReplayResponse)
async def replay_session(
    session_id: str,
    mode: str = Query(default="full", pattern="^(full|focus|failure)$"),
    focus_event_id: str | None = Query(default=None),
    breakpoint_event_types: str | None = Query(default=None),
    breakpoint_tool_names: str | None = Query(default=None),
    breakpoint_confidence_below: float | None = Query(default=None, ge=0.0, le=1.0),
    breakpoint_safety_outcomes: str | None = Query(default=None),
    repo: TraceRepository = Depends(get_repository),
) -> ReplayResponse:
    await require_session(repo, session_id)
    events, checkpoints = await load_session_artifacts(repo, session_id)

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
    )
