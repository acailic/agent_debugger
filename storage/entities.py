"""Entity extraction from trace events.

This module provides functionality to extract and index entities from trace events,
including tool names, error types, API endpoints, agent names, and other key entities.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Entity:
    """A single extracted entity with frequency metadata."""

    entity_type: str
    value: str
    count: int = 1
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    session_ids: set[str] = field(default_factory=set)
    sample_event_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "entity_type": self.entity_type,
            "value": self.value,
            "count": self.count,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "session_count": len(self.session_ids),
            "sample_event_ids": self.sample_event_ids[:5],  # Limit to 5 samples
        }


class EntityType:
    """Entity types that can be extracted from trace events."""

    TOOL_NAME = "tool_name"
    ERROR_TYPE = "error_type"
    MODEL = "model"
    AGENT_NAME = "agent_name"
    POLICY_NAME = "policy_name"
    ALERT_TYPE = "alert_type"
    VIOLATION_TYPE = "violation_type"
    API_ENDPOINT = "api_endpoint"
    SAFE_ALTERNATIVE = "safe_alternative"


class EntityExtractor:
    """Extract entities from trace events.

    Parses tool names, error types, API endpoints, agent names, and other key
    entities from trace event data and metadata.
    """

    # Patterns for extracting API endpoints from tool names or arguments
    API_ENDPOINT_PATTERNS = [
        re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE),
        re.compile(r"/[a-z_]+/[a-z_]+", re.IGNORECASE),
        re.compile(r"[a-z]+\.[a-z]+\.[a-z]+", re.IGNORECASE),
    ]

    def __init__(self, max_samples: int = 5):
        """Initialize the entity extractor.

        Args:
            max_samples: Maximum number of sample event IDs to store per entity
        """
        self.max_samples = max_samples

    def extract_from_events(self, events: list[dict[str, Any]]) -> dict[str, Entity]:
        """Extract entities from a list of event dictionaries.

        Args:
            events: List of event dictionaries with 'data', 'metadata', 'event_type',
                   'id', 'session_id', and 'timestamp' fields

        Returns:
            Dictionary mapping entity_key to Entity instances
        """
        entities: dict[str, Entity] = defaultdict(self._create_entity)

        for event in events:
            self._extract_from_event(event, entities)

        return dict(entities)

    def _create_entity(self) -> Entity:
        """Factory function for defaultdict."""
        return Entity(entity_type="", value="")

    def _extract_from_event(self, event: dict[str, Any], entities: dict[str, Entity]) -> None:
        """Extract entities from a single event.

        Args:
            event: Event dictionary
            entities: Dictionary to populate with extracted entities
        """
        event_data = event.get("data", {})
        event_metadata = event.get("event_metadata", {})
        event_id = event.get("id", "")
        session_id = event.get("session_id", "")
        timestamp = event.get("timestamp", "")

        # Extract tool names
        tool_name = event_data.get("tool_name") or event_metadata.get("tool_name")
        if tool_name:
            self._add_entity(
                entities,
                EntityType.TOOL_NAME,
                tool_name,
                event_id,
                session_id,
                timestamp,
            )

        # Extract error types
        error_type = event_data.get("error_type")
        if error_type:
            self._add_entity(
                entities,
                EntityType.ERROR_TYPE,
                error_type,
                event_id,
                session_id,
                timestamp,
            )

        # Extract model names
        model = event_data.get("model")
        if model:
            self._add_entity(
                entities,
                EntityType.MODEL,
                model,
                event_id,
                session_id,
                timestamp,
            )

        # Extract policy names
        policy_name = event_data.get("policy_name")
        if policy_name:
            self._add_entity(
                entities,
                EntityType.POLICY_NAME,
                policy_name,
                event_id,
                session_id,
                timestamp,
            )

        # Extract alert types
        alert_type = event_data.get("alert_type")
        if alert_type:
            self._add_entity(
                entities,
                EntityType.ALERT_TYPE,
                alert_type,
                event_id,
                session_id,
                timestamp,
            )

        # Extract violation types
        violation_type = event_data.get("violation_type")
        if violation_type:
            self._add_entity(
                entities,
                EntityType.VIOLATION_TYPE,
                violation_type,
                event_id,
                session_id,
                timestamp,
            )

        # Extract safe alternatives
        safe_alternative = event_data.get("safe_alternative")
        if safe_alternative:
            self._add_entity(
                entities,
                EntityType.SAFE_ALTERNATIVE,
                safe_alternative,
                event_id,
                session_id,
                timestamp,
            )

        # Extract API endpoints from tool arguments
        arguments = event_data.get("arguments", {})
        if isinstance(arguments, dict):
            for value in arguments.values():
                if isinstance(value, str):
                    endpoints = self._extract_api_endpoints(value)
                    for endpoint in endpoints:
                        self._add_entity(
                            entities,
                            EntityType.API_ENDPOINT,
                            endpoint,
                            event_id,
                            session_id,
                            timestamp,
                        )

    def _add_entity(
        self,
        entities: dict[str, Entity],
        entity_type: str,
        value: str,
        event_id: str,
        session_id: str,
        timestamp: str,
    ) -> None:
        """Add or update an entity in the collection.

        Args:
            entities: Dictionary of entities
            entity_type: Type of the entity
            value: Entity value
            event_id: Event ID to add to samples
            session_id: Session ID to track
            timestamp: Event timestamp
        """
        key = f"{entity_type}:{value}"
        if key in entities:
            entity = entities[key]
            entity.count += 1
            entity.session_ids.add(session_id)
            if len(entity.sample_event_ids) < self.max_samples:
                entity.sample_event_ids.append(event_id)
            entity.last_seen_at = timestamp
        else:
            entities[key] = Entity(
                entity_type=entity_type,
                value=value,
                count=1,
                first_seen_at=timestamp,
                last_seen_at=timestamp,
                session_ids={session_id},
                sample_event_ids=[event_id],
            )

    def _extract_api_endpoints(self, text: str) -> list[str]:
        """Extract API endpoints from text.

        Args:
            text: Text to search for endpoints

        Returns:
            List of extracted endpoint strings
        """
        endpoints = []
        for pattern in self.API_ENDPOINT_PATTERNS:
            matches = pattern.findall(text)
            endpoints.extend(matches)
        return list(set(endpoints))


def rank_entities(entities: dict[str, Entity], sort_by: str = "count") -> list[Entity]:
    """Rank entities by a specified metric.

    Args:
        entities: Dictionary of entities
        sort_by: Metric to sort by ('count', 'session_count', 'value')

    Returns:
        List of entities sorted by the specified metric
    """
    entity_list = list(entities.values())

    if sort_by == "count":
        entity_list.sort(key=lambda e: e.count, reverse=True)
    elif sort_by == "session_count":
        entity_list.sort(key=lambda e: len(e.session_ids), reverse=True)
    elif sort_by == "value":
        entity_list.sort(key=lambda e: e.value.lower())
    else:
        entity_list.sort(key=lambda e: e.count, reverse=True)

    return entity_list


def filter_entities_by_type(entities: dict[str, Entity], entity_type: str) -> dict[str, Entity]:
    """Filter entities by type.

    Args:
        entities: Dictionary of entities
        entity_type: Entity type to filter by

    Returns:
        Dictionary of entities matching the specified type
    """
    return {k: v for k, v in entities.items() if v.entity_type == entity_type}


def get_top_entities(
    entities: dict[str, Entity],
    entity_type: str | None = None,
    limit: int = 10,
    sort_by: str = "count",
) -> list[dict[str, Any]]:
    """Get top entities by type and metric.

    Args:
        entities: Dictionary of entities
        entity_type: Optional entity type to filter by
        limit: Maximum number of entities to return
        sort_by: Metric to sort by ('count', 'session_count', 'value')

    Returns:
        List of entity dictionaries sorted by the specified metric
    """
    if entity_type:
        filtered = filter_entities_by_type(entities, entity_type)
    else:
        filtered = entities

    ranked = rank_entities(filtered, sort_by=sort_by)
    return [entity.to_dict() for entity in ranked[:limit]]
