"""Agent stepper API routes for interactive breakpoint and step-through debugging.

Provides endpoints for setting breakpoints, stepping through execution,
inspecting agent state, and creating alternative execution branches.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from agent_debugger_sdk.core.stepper import (
    AgentStepper,
    BreakpointType,
    StepAction,
)
from api.dependencies import get_repository
from api.services import (
    load_session_artifacts,
    require_session,
)
from storage import TraceRepository

router = APIRouter(tags=["stepper"])

# In-memory stepper instances (in production, use Redis or database)
stepper_instances: dict[str, AgentStepper] = {}


def _get_stepper(session_id: str) -> AgentStepper:
    """Get or create stepper instance for a session.

    Args:
        session_id: Session ID to get stepper for

    Returns:
        AgentStepper instance
    """
    if session_id not in stepper_instances:
        stepper_instances[session_id] = AgentStepper()
    return stepper_instances[session_id]


@router.post("/api/sessions/{session_id}/breakpoints")
async def set_breakpoint(
    session_id: str,
    breakpoint_type: BreakpointType,
    condition_value: Any = None,
    description: str = "",
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Set a breakpoint for agent execution debugging.

    Args:
        session_id: Session ID to set breakpoint for
        breakpoint_type: Type of breakpoint condition
        condition_value: Value for the breakpoint condition
        description: Human-readable description

    Returns:
        Created breakpoint with stepper state
    """
    # Verify session exists
    await require_session(repo, session_id)

    # Get stepper and set breakpoint
    stepper = _get_stepper(session_id)
    breakpoint = stepper.set_breakpoint(
        breakpoint_type=breakpoint_type,
        condition_value=condition_value,
        description=description,
    )

    return {
        "session_id": session_id,
        "breakpoint": breakpoint.to_dict(),
        "stepper_state": stepper.state.to_dict(),
    }


@router.delete("/api/sessions/{session_id}/breakpoints/{breakpoint_id}")
async def clear_breakpoint(
    session_id: str,
    breakpoint_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Clear a breakpoint by ID.

    Args:
        session_id: Session ID
        breakpoint_id: Breakpoint ID to clear

    Returns:
        Success status and updated stepper state
    """
    # Verify session exists
    await require_session(repo, session_id)

    # Get stepper and clear breakpoint
    stepper = _get_stepper(session_id)
    success = stepper.clear_breakpoint(breakpoint_id)

    return {
        "session_id": session_id,
        "success": success,
        "stepper_state": stepper.state.to_dict(),
    }


@router.delete("/api/sessions/{session_id}/breakpoints")
async def clear_all_breakpoints(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Clear all breakpoints for a session.

    Args:
        session_id: Session ID

    Returns:
        Success status and updated stepper state
    """
    # Verify session exists
    await require_session(repo, session_id)

    # Get stepper and clear all breakpoints
    stepper = _get_stepper(session_id)
    stepper.clear_all_breakpoints()

    return {
        "session_id": session_id,
        "success": True,
        "breakpoints_cleared": len(stepper.state.breakpoints),
        "stepper_state": stepper.state.to_dict(),
    }


@router.get("/api/sessions/{session_id}/breakpoints")
async def list_breakpoints(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """List all breakpoints for a session.

    Args:
        session_id: Session ID

    Returns:
        List of active breakpoints
    """
    # Verify session exists
    await require_session(repo, session_id)

    # Get stepper and list breakpoints
    stepper = _get_stepper(session_id)

    return {
        "session_id": session_id,
        "breakpoints": [bp.to_dict() for bp in stepper.state.breakpoints],
    }


@router.post("/api/sessions/{session_id}/step")
async def step_execution(
    session_id: str,
    action: StepAction,
    target_event_id: str | None = None,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Execute a step action in agent execution.

    Args:
        session_id: Session ID
        action: Step action to perform
        target_event_id: Target event ID for STEP_OVER or RUN_TO

    Returns:
        StepResult with current event and state
    """
    # Load session events
    await require_session(repo, session_id)
    events, _ = await load_session_artifacts(repo, session_id)

    # Get or create stepper with events
    stepper = _get_stepper(session_id)
    if not stepper.events:
        stepper.events = events
        stepper._build_event_index()

    # Execute step
    result = stepper.step(action, target_event_id)

    return {
        "session_id": session_id,
        "step_result": result.to_dict(),
    }


@router.get("/api/sessions/{session_id}/state")
async def get_stepper_state(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get agent state at current stepper position.

    Args:
        session_id: Session ID

    Returns:
        Current agent state and stepper position
    """
    # Load session events
    await require_session(repo, session_id)
    events, _ = await load_session_artifacts(repo, session_id)

    # Get or create stepper with events
    stepper = _get_stepper(session_id)
    if not stepper.events:
        stepper.events = events
        stepper._build_event_index()

    # Get state at current position
    agent_state = stepper.get_state_at_current_position()

    return {
        "session_id": session_id,
        "agent_state": agent_state,
        "stepper_state": stepper.state.to_dict(),
    }


@router.post("/api/sessions/{session_id}/branch")
async def create_branch(
    session_id: str,
    name: str,
    parent_event_id: str,
    description: str = "",
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Create a branch point for alternative path exploration.

    Args:
        session_id: Session ID
        name: Human-readable name for the branch
        parent_event_id: Event where branch starts
        description: What this branch explores

    Returns:
        Created branch point
    """
    # Load session events
    await require_session(repo, session_id)
    events, _ = await load_session_artifacts(repo, session_id)

    # Get or create stepper with events
    stepper = _get_stepper(session_id)
    if not stepper.events:
        stepper.events = events
        stepper._build_event_index()

    # Create branch
    branch = stepper.create_branch(
        name=name,
        parent_event_id=parent_event_id,
        description=description,
    )

    return {
        "session_id": session_id,
        "branch": branch.to_dict(),
    }


@router.get("/api/sessions/{session_id}/branches")
async def list_branches(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """List all branches for a session.

    Args:
        session_id: Session ID

    Returns:
        List of all branches
    """
    # Verify session exists
    await require_session(repo, session_id)

    # Get stepper and list branches
    stepper = _get_stepper(session_id)

    return {
        "session_id": session_id,
        "branches": [branch.to_dict() for branch in stepper.list_branches()],
    }


@router.get("/api/sessions/{session_id}/branches/{branch_id}")
async def get_branch(
    session_id: str,
    branch_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get a specific branch by ID.

    Args:
        session_id: Session ID
        branch_id: Branch ID to retrieve

    Returns:
        Branch details
    """
    # Verify session exists
    await require_session(repo, session_id)

    # Get stepper and branch
    stepper = _get_stepper(session_id)
    branch = stepper.get_branch(branch_id)

    if not branch:
        return {
            "session_id": session_id,
            "branch_id": branch_id,
            "error": "Branch not found",
        }

    return {
        "session_id": session_id,
        "branch": branch.to_dict(),
    }


@router.delete("/api/sessions/{session_id}/branches/{branch_id}")
async def delete_branch(
    session_id: str,
    branch_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Delete a branch by ID.

    Args:
        session_id: Session ID
        branch_id: Branch ID to delete

    Returns:
        Success status
    """
    # Verify session exists
    await require_session(repo, session_id)

    # Get stepper and delete branch
    stepper = _get_stepper(session_id)
    success = stepper.delete_branch(branch_id)

    return {
        "session_id": session_id,
        "branch_id": branch_id,
        "success": success,
    }


@router.post("/api/sessions/{session_id}/stepper/reset")
async def reset_stepper(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Reset stepper to initial state.

    Args:
        session_id: Session ID

    Returns:
        Reset status and new stepper state
    """
    # Verify session exists
    await require_session(repo, session_id)

    # Get stepper and reset
    stepper = _get_stepper(session_id)
    stepper.reset()

    return {
        "session_id": session_id,
        "success": True,
        "stepper_state": stepper.state.to_dict(),
    }


@router.get("/api/sessions/{session_id}/stepper/context")
async def get_execution_context(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get full execution context with state and branches.

    Args:
        session_id: Session ID

    Returns:
        Complete execution context
    """
    # Load session events
    await require_session(repo, session_id)
    events, _ = await load_session_artifacts(repo, session_id)

    # Get or create stepper with events
    stepper = _get_stepper(session_id)
    if not stepper.events:
        stepper.events = events
        stepper._build_event_index()

    # Get execution context
    context = stepper.get_execution_context()

    return {
        "session_id": session_id,
        "execution_context": context,
    }
