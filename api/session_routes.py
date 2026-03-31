"""Session-oriented API routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse

from api.config import MAX_SESSIONS_PER_PAGE, MAX_TRACES_PER_REQUEST
from api.dependencies import get_repository
from api.schemas import (
    CheckpointDeltaSchema,
    CheckpointDeltasResponse,
    CheckpointListResponse,
    DecisionTreeResponse,
    DeleteResponse,
    FixNoteRequest,
    FixNoteResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionUpdateRequest,
    TraceListResponse,
)
from api.services import (
    compute_checkpoint_deltas,
    enrich_sessions_for_listing,
    event_generator,
    normalize_checkpoint,
    normalize_event,
    normalize_session,
    require_session,
)
from storage import TraceRepository

router = APIRouter(tags=["sessions"])


@router.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=MAX_SESSIONS_PER_PAGE),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="started_at", pattern="^(started_at|replay_value)$"),
    repo: TraceRepository = Depends(get_repository),
) -> SessionListResponse:
    total = await repo.count_sessions()
    sessions = await repo.list_sessions(limit=limit, offset=offset, sort_by=sort_by)
    return SessionListResponse(
        sessions=await enrich_sessions_for_listing(repo, sessions, sort_by=sort_by),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> SessionDetailResponse:
    session = await require_session(repo, session_id)
    return SessionDetailResponse(session=normalize_session(session))


@router.put("/api/sessions/{session_id}", response_model=SessionDetailResponse)
async def update_session(
    session_id: str,
    update: SessionUpdateRequest,
    repo: TraceRepository = Depends(get_repository),
) -> SessionDetailResponse:
    update_data = update.model_dump(exclude_none=True)
    session = await repo.update_session(session_id, **update_data)
    if session is None:
        session = await require_session(repo, session_id)
    else:
        await repo.commit()
    return SessionDetailResponse(session=normalize_session(session))


@router.delete("/api/sessions/{session_id}", response_model=DeleteResponse)
async def delete_session(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> DeleteResponse:
    await require_session(repo, session_id)
    await repo.delete_session(session_id)
    await repo.commit()
    return DeleteResponse(deleted=True, session_id=session_id)


@router.get("/api/sessions/{session_id}/traces", response_model=TraceListResponse)
async def get_session_traces(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=MAX_TRACES_PER_REQUEST),
    offset: int = Query(default=0, ge=0),
    repo: TraceRepository = Depends(get_repository),
) -> TraceListResponse:
    await require_session(repo, session_id)
    traces = await repo.list_events(session_id, limit=limit, offset=offset)
    return TraceListResponse(
        traces=[normalize_event(trace) for trace in traces],
        session_id=session_id,
    )


@router.get("/api/sessions/{session_id}/tree", response_model=DecisionTreeResponse)
async def get_decision_tree(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> DecisionTreeResponse:
    await require_session(repo, session_id)
    events = await repo.get_event_tree(session_id)
    return DecisionTreeResponse(
        session_id=session_id,
        events=[normalize_event(event) for event in events],
    )


@router.get("/api/sessions/{session_id}/checkpoints", response_model=CheckpointListResponse)
async def list_checkpoints(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> CheckpointListResponse:
    await require_session(repo, session_id)
    checkpoints = await repo.list_checkpoints(session_id)
    return CheckpointListResponse(
        checkpoints=[normalize_checkpoint(checkpoint) for checkpoint in checkpoints],
        session_id=session_id,
    )


@router.get("/api/sessions/{session_id}/checkpoints/deltas", response_model=CheckpointDeltasResponse)
async def get_checkpoint_deltas(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> CheckpointDeltasResponse:
    """Get state and memory deltas between consecutive checkpoints.

    Returns a list of deltas comparing each checkpoint with its predecessor,
    showing what changed in state and memory between checkpoints.
    """
    await require_session(repo, session_id)
    checkpoints = await repo.list_checkpoints(session_id)
    deltas = compute_checkpoint_deltas(checkpoints)
    return CheckpointDeltasResponse(
        deltas=[CheckpointDeltaSchema(**delta) for delta in deltas],
        session_id=session_id,
    )


@router.get("/api/sessions/{session_id}/stream")
async def stream_session_events(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> StreamingResponse:
    await require_session(repo, session_id)
    return StreamingResponse(
        event_generator(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> JSONResponse:
    session = await require_session(repo, session_id)
    events = await repo.list_events(session_id, limit=MAX_TRACES_PER_REQUEST)
    # Add limit to checkpoint loading to prevent unbounded queries
    checkpoints = await repo.list_checkpoints(session_id, limit=1000)

    export_data = {
        "export_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session": session.to_dict(),
        "events": [event.to_dict() for event in events],
        "checkpoints": [checkpoint.to_dict() for checkpoint in checkpoints],
    }

    return JSONResponse(
        content=export_data,
        headers={"Content-Disposition": f'attachment; filename="session_{session_id}_export.json"'},
    )


@router.post("/api/sessions/{session_id}/fix-note", response_model=FixNoteResponse)
async def add_fix_note(
    session_id: str,
    request: FixNoteRequest,
    repo: TraceRepository = Depends(get_repository),
) -> FixNoteResponse:
    await require_session(repo, session_id)
    updated_session = await repo.add_fix_note(session_id, request.note)
    if updated_session:
        await repo.commit()
    return FixNoteResponse(session_id=session_id, fix_note=request.note)
