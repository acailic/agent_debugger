"""Entity extraction and analysis API routes.

This module provides API endpoints for querying extracted entities from trace events,
including top tools, error types, models, and entity frequency statistics.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.dependencies import get_entity_repository
from storage.entities import EntityType

router = APIRouter(tags=["entities"])


class EntityItem(BaseModel):
    """Schema for a single entity with statistics."""

    entity_type: str
    value: str
    count: int
    first_seen_at: str | None
    last_seen_at: str | None
    session_count: int
    sample_event_ids: list[str]


class EntityListResponse(BaseModel):
    """Response schema for entity lists."""

    entity_type: str | None
    total: int
    limit: int
    sort_by: str
    entities: list[EntityItem]


class EntitySummaryResponse(BaseModel):
    """Response schema for entity summary statistics."""

    agent_name_count: int
    tool_name_count: int
    error_type_count: int
    model_count: int
    policy_name_count: int
    alert_type_count: int
    violation_type_count: int
    api_endpoint_count: int
    safe_alternative_count: int


@router.get(
    "/api/entities",
    response_model=EntityListResponse,
)
async def get_entities(
    entity_type: str | None = Query(
        default=None, description="Filter by entity type (e.g., 'tool_name', 'error_type')"
    ),
    limit: int = Query(default=10, ge=1, le=100, description="Maximum number of entities to return"),
    sort_by: str = Query(default="count", pattern="^(count|session_count|value)$", description="Sort metric"),
    repo = Depends(get_entity_repository),
) -> EntityListResponse:
    """Get top entities by type and metric.

    Returns entities extracted from trace events, including tool names,
    error types, models, and other key entities. Results can be filtered
    by entity type and sorted by count, session count, or value.
    """
    entities = await repo.get_top_entities(entity_type=entity_type, limit=limit, sort_by=sort_by)

    return EntityListResponse(
        entity_type=entity_type,
        total=len(entities),
        limit=limit,
        sort_by=sort_by,
        entities=[EntityItem(**entity) for entity in entities],
    )


@router.get("/api/entities/tools", response_model=EntityListResponse)
async def get_top_tools(
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of tools to return"),
    sort_by: str = Query(default="count", pattern="^(count|session_count)$", description="Sort metric"),
    repo = Depends(get_entity_repository),
) -> EntityListResponse:
    """Get top tools by usage frequency.

    Returns the most frequently used tools across all trace events.
    Can be sorted by total usage count or by number of unique sessions.
    """
    entities = await repo.get_top_tools(limit=limit, sort_by=sort_by)

    return EntityListResponse(
        entity_type=EntityType.TOOL_NAME,
        total=len(entities),
        limit=limit,
        sort_by=sort_by,
        entities=[EntityItem(**entity) for entity in entities],
    )


@router.get("/api/entities/errors", response_model=EntityListResponse)
async def get_top_errors(
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of error types to return"),
    sort_by: str = Query(default="count", pattern="^(count|session_count)$", description="Sort metric"),
    repo = Depends(get_entity_repository),
) -> EntityListResponse:
    """Get top error types by occurrence frequency.

    Returns the most common error types across all trace events.
    Useful for identifying failure-prone areas and prioritizing fixes.
    """
    entities = await repo.get_top_errors(limit=limit, sort_by=sort_by)

    return EntityListResponse(
        entity_type=EntityType.ERROR_TYPE,
        total=len(entities),
        limit=limit,
        sort_by=sort_by,
        entities=[EntityItem(**entity) for entity in entities],
    )


@router.get("/api/entities/models", response_model=EntityListResponse)
async def get_top_models(
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of models to return"),
    repo = Depends(get_entity_repository),
) -> EntityListResponse:
    """Get top LLM models by usage frequency.

    Returns the most frequently used LLM models across all trace events.
    Useful for understanding model usage patterns and costs.
    """
    entities = await repo.get_top_models(limit=limit)

    return EntityListResponse(
        entity_type=EntityType.MODEL,
        total=len(entities),
        limit=limit,
        sort_by="count",
        entities=[EntityItem(**entity) for entity in entities],
    )


@router.get("/api/entities/summary", response_model=EntitySummaryResponse)
async def get_entity_summary(
    repo = Depends(get_entity_repository),
) -> EntitySummaryResponse:
    """Get entity summary statistics.

    Returns counts for each entity type extracted from trace events.
    Provides a high-level overview of the entity distribution.
    """
    summary = await repo.get_entity_summary()

    return EntitySummaryResponse(
        agent_name_count=summary.get(EntityType.AGENT_NAME, 0),
        tool_name_count=summary.get(EntityType.TOOL_NAME, 0),
        error_type_count=summary.get(EntityType.ERROR_TYPE, 0),
        model_count=summary.get(EntityType.MODEL, 0),
        policy_name_count=summary.get(EntityType.POLICY_NAME, 0),
        alert_type_count=summary.get(EntityType.ALERT_TYPE, 0),
        violation_type_count=summary.get(EntityType.VIOLATION_TYPE, 0),
        api_endpoint_count=summary.get(EntityType.API_ENDPOINT, 0),
        safe_alternative_count=summary.get(EntityType.SAFE_ALTERNATIVE, 0),
    )
