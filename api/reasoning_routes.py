"""Reasoning editing API routes (#192).

Provides endpoints for interactive Chain-of-Thought editing and live replay,
based on IUI 2026 paper "Interactive Reasoning: Visualizing and Controlling
Chain-of-Thought Reasoning in LMs" by Pang et al.

Key capabilities:
- Edit reasoning steps in DecisionEvent and LLM events
- Create execution branches from modified reasoning
- Live replay with alternative reasoning paths
- Scenario management for comparing edited executions
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from agent_debugger_sdk.core.events import TraceEvent
from agent_debugger_sdk.core.reasoning_editor import (
    EditOperation,
    ReasoningEdit,
    ReasoningEditor,
    ScenarioBranch,
)
from api.dependencies import get_repository
from api.services import load_session_artifacts, require_session
from storage import TraceRepository

__all__ = ["router"]

router = APIRouter(tags=["reasoning"])


# =============================================================================
# Request/Response Schemas
# =============================================================================


class ReasoningEditRequest(BaseModel):
    """Request schema for creating a reasoning edit."""

    event_id: str = Field(..., description="ID of the event to edit")
    operation: str = Field(..., description="Type of edit operation (modify, insert, delete, replace)")
    field_name: str = Field(default="reasoning", description="Field to edit (default: reasoning)")
    new_value: Any = Field(default=None, description="New value to set")
    position: int = Field(default=-1, description="Position for INSERT operations")


class ScenarioBranchRequest(BaseModel):
    """Request schema for creating a scenario branch."""

    name: str = Field(..., description="Human-readable name for the scenario")
    parent_event_id: str = Field(..., description="Event where branch diverges")
    description: str = Field(default="", description="What changes this branch introduces")
    edits: list[ReasoningEditRequest] = Field(default_factory=list, description="Edits to apply in this branch")


class ReasoningEditResponse(BaseModel):
    """Response schema for reasoning edit operations."""

    edit_id: str
    operation: str
    event_id: str
    field_name: str
    old_value: Any
    new_value: Any
    position: int
    created_at: str


class ScenarioBranchResponse(BaseModel):
    """Response schema for scenario branch operations."""

    branch_id: str
    name: str
    description: str
    parent_event_id: str
    edits: list[ReasoningEditResponse]
    original_session_id: str
    created_at: str
    replay_result: dict[str, Any] | None = None


class HierarchicalReasoningResponse(BaseModel):
    """Response schema for hierarchical reasoning extraction."""

    topics: list[dict[str, Any]]
    raw: str


class ScenarioComparisonResponse(BaseModel):
    """Response schema for scenario comparison."""

    branches: list[dict[str, Any]]
    differences: list[dict[str, Any]]
    metrics: dict[str, Any]


# =============================================================================
# Core Reasoning Editing Endpoints
# =============================================================================


@router.post("/api/sessions/{session_id}/reasoning/edit")
async def edit_reasoning(
    session_id: str,
    edit_request: ReasoningEditRequest,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Edit reasoning content in a session event.

    Allows modification, insertion, deletion, or replacement of reasoning
    content in DecisionEvent and LLM events.

    Args:
        session_id: Session containing the event to edit
        edit_request: Edit operation details

    Returns:
        Created reasoning edit with metadata
    """
    # Load session
    await require_session(repo, session_id)

    # Load events
    events, _ = await load_session_artifacts(repo, session_id)

    # Create editor and apply edit
    editor = ReasoningEditor(events=events)

    try:
        operation = EditOperation(edit_request.operation)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid operation: {edit_request.operation}. Must be one of: modify, insert, delete, replace"
        )

    try:
        edit = editor.edit_reasoning(
            event_id=edit_request.event_id,
            operation=operation,
            field_name=edit_request.field_name,
            new_value=edit_request.new_value,
            position=edit_request.position,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "session_id": session_id,
        "edit": _reasoning_edit_to_response(edit),
        "modified_event": _event_to_dict(editor.get_event_by_id(edit_request.event_id)),
    }


@router.post("/api/sessions/{session_id}/reasoning/branch")
async def create_scenario_branch(
    session_id: str,
    branch_request: ScenarioBranchRequest,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Create a scenario branch with modified reasoning.

    Creates an alternative execution path by branching from a specific event
    and applying reasoning edits.

    Args:
        session_id: Original session to branch from
        branch_request: Branch configuration

    Returns:
        Created scenario branch with all edits applied
    """
    # Load session
    await require_session(repo, session_id)

    # Load events
    events, _ = await load_session_artifacts(repo, session_id)

    # Create editor
    editor = ReasoningEditor(events=events)

    # Convert edit requests to ReasoningEdit objects
    edits = []
    for edit_request in branch_request.edits:
        try:
            operation = EditOperation(edit_request.operation)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid operation: {edit_request.operation}"
            )

        # Get old value
        event = editor.get_event_by_id(edit_request.event_id)
        if not event:
            raise HTTPException(
                status_code=404,
                detail=f"Event {edit_request.event_id} not found"
            )

        old_value = getattr(event, edit_request.field_name, None) or event.data.get(edit_request.field_name, "")

        edit = ReasoningEdit(
            operation=operation,
            event_id=edit_request.event_id,
            field_name=edit_request.field_name,
            old_value=old_value,
            new_value=edit_request.new_value,
            position=edit_request.position,
        )
        edits.append(edit)

    # Create branch
    branch = editor.create_branch(
        name=branch_request.name,
        parent_event_id=branch_request.parent_event_id,
        description=branch_request.description,
        edits=edits,
    )

    return {
        "session_id": session_id,
        "branch": _scenario_branch_to_response(branch),
    }


@router.get("/api/sessions/{session_id}/reasoning/replay")
async def get_replay_events(
    session_id: str,
    from_event_id: str,
    branch_id: str | None = None,
    include_branch_edits: bool = Query(default=True, description="Include branch edits in replay"),
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get events for replay starting from a specific event.

    Returns events in execution order, optionally with branch edits applied.

    Args:
        session_id: Session containing events
        from_event_id: Event ID to start replay from
        branch_id: Optional branch to get edits from
        include_branch_edits: Whether to include branch edits

    Returns:
        List of events in replay order
    """
    # Load session
    await require_session(repo, session_id)

    # Load events
    events, _ = await load_session_artifacts(repo, session_id)

    # Create editor
    editor = ReasoningEditor(events=events)

    try:
        replay_events = editor.get_events_for_replay(
            from_event_id=from_event_id,
            include_branch_edits=include_branch_edits,
            branch_id=branch_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "session_id": session_id,
        "from_event_id": from_event_id,
        "branch_id": branch_id,
        "replay_events": [_event_to_dict(event) for event in replay_events],
        "replay_count": len(replay_events),
    }


@router.get("/api/sessions/{session_id}/reasoning/hierarchical")
async def get_hierarchical_reasoning(
    session_id: str,
    event_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get hierarchical reasoning structure from an event.

    Based on IUI 2026 paper's topic hierarchy visualization, structures
    reasoning as a tree of topics/subtopics.

    Args:
        session_id: Session containing the event
        event_id: Event to extract reasoning from

    Returns:
        Hierarchical structure with topics, subtopics, and content
    """
    # Load session
    await require_session(repo, session_id)

    # Load events
    events, _ = await load_session_artifacts(repo, session_id)

    # Create editor
    editor = ReasoningEditor(events=events)

    hierarchy = editor.get_hierarchical_reasoning(event_id)

    return {
        "session_id": session_id,
        "event_id": event_id,
        "hierarchical_reasoning": hierarchy,
    }


# =============================================================================
# Scenario Management Endpoints
# =============================================================================


@router.get("/api/sessions/{session_id}/reasoning/scenarios")
async def list_scenarios(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """List all scenario branches for a session.

    Args:
        session_id: Session to list scenarios for

    Returns:
        List of all scenario branches
    """
    # Load session
    await require_session(repo, session_id)

    # Load events
    events, _ = await load_session_artifacts(repo, session_id)

    # Create editor
    editor = ReasoningEditor(events=events)

    scenarios = [
        _scenario_branch_to_response(branch)
        for branch in editor.scenarios.values()
        if branch.original_session_id == session_id
    ]

    return {
        "session_id": session_id,
        "scenarios": scenarios,
        "total_count": len(scenarios),
    }


@router.get("/api/sessions/{session_id}/reasoning/scenarios/{branch_id}")
async def get_scenario(
    session_id: str,
    branch_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get a specific scenario branch.

    Args:
        session_id: Session containing the scenario
        branch_id: Branch ID to retrieve

    Returns:
        Scenario branch details
    """
    # Load session
    await require_session(repo, session_id)

    # Load events
    events, _ = await load_session_artifacts(repo, session_id)

    # Create editor
    editor = ReasoningEditor(events=events)

    branch = editor.scenarios.get(branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail=f"Branch {branch_id} not found")

    return {
        "session_id": session_id,
        "branch": _scenario_branch_to_response(branch),
    }


@router.get("/api/sessions/{session_id}/reasoning/scenarios/compare")
async def compare_scenarios(
    session_id: str,
    branch_ids: list[str] = Query(..., description="List of branch IDs to compare"),
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Compare multiple scenario branches.

    Args:
        session_id: Session containing scenarios
        branch_ids: List of branch IDs to compare

    Returns:
        Comparison with metrics, differences, and recommendations
    """
    # Load session
    await require_session(repo, session_id)

    # Load events
    events, _ = await load_session_artifacts(repo, session_id)

    # Create editor
    editor = ReasoningEditor(events=events)

    # Validate all branches exist
    for branch_id in branch_ids:
        if branch_id not in editor.scenarios:
            raise HTTPException(status_code=404, detail=f"Branch {branch_id} not found")

    comparison = editor.compare_scenarios(branch_ids)

    return {
        "session_id": session_id,
        "comparison": comparison,
    }


@router.get("/api/sessions/{session_id}/reasoning/scenarios/{branch_id}/export")
async def export_scenario(
    session_id: str,
    branch_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Export a scenario as JSON-serializable dict.

    Args:
        session_id: Session containing the scenario
        branch_id: Branch ID to export

    Returns:
        JSON-serializable representation of the scenario
    """
    # Load session
    await require_session(repo, session_id)

    # Load events
    events, _ = await load_session_artifacts(repo, session_id)

    # Create editor
    editor = ReasoningEditor(events=events)

    try:
        exported = editor.export_scenario(branch_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "session_id": session_id,
        "exported_scenario": exported,
    }


@router.post("/api/sessions/{session_id}/reasoning/scenarios/import")
async def import_scenario(
    session_id: str,
    scenario_data: dict[str, Any],
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Import a scenario from exported data.

    Args:
        session_id: Session to import scenario into
        scenario_data: Exported scenario data

    Returns:
        Imported scenario branch
    """
    # Load session
    await require_session(repo, session_id)

    # Load events
    events, _ = await load_session_artifacts(repo, session_id)

    # Create editor
    editor = ReasoningEditor(events=events)

    try:
        imported_branch = editor.import_scenario(scenario_data)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid scenario data: {str(e)}")

    return {
        "session_id": session_id,
        "imported_branch": _scenario_branch_to_response(imported_branch),
    }


# =============================================================================
# Helper Functions
# =============================================================================


def _reasoning_edit_to_response(edit: ReasoningEdit) -> ReasoningEditResponse:
    """Convert ReasoningEdit to response schema."""
    return ReasoningEditResponse(
        edit_id=edit.edit_id,
        operation=edit.operation.value,
        event_id=edit.event_id,
        field_name=edit.field_name,
        old_value=edit.old_value,
        new_value=edit.new_value,
        position=edit.position,
        created_at=edit.created_at.isoformat(),
    )


def _scenario_branch_to_response(branch: ScenarioBranch) -> ScenarioBranchResponse:
    """Convert ScenarioBranch to response schema."""
    return ScenarioBranchResponse(
        branch_id=branch.branch_id,
        name=branch.name,
        description=branch.description,
        parent_event_id=branch.parent_event_id,
        edits=[_reasoning_edit_to_response(edit) for edit in branch.edits],
        original_session_id=branch.original_session_id,
        created_at=branch.created_at.isoformat(),
        replay_result=branch.replay_result,
    )


def _event_to_dict(event: TraceEvent) -> dict[str, Any]:
    """Convert TraceEvent to dict for JSON response."""
    event_dict = event.to_dict()

    # Handle datetime serialization
    if "timestamp" in event_dict and event_dict["timestamp"]:
        if hasattr(event_dict["timestamp"], "isoformat"):
            event_dict["timestamp"] = event_dict["timestamp"].isoformat()
        else:
            event_dict["timestamp"] = str(event_dict["timestamp"])

    return event_dict
