"""Tests for entity extraction from trace events."""

from __future__ import annotations

import pytest

from storage.entities import (
    Entity,
    EntityExtractor,
    EntityType,
    filter_entities_by_type,
    get_top_entities,
    rank_entities,
)


@pytest.mark.parametrize(
    ("events", "expected_count", "expected_type"),
    [
        # Single tool name extraction
        (
            [
                {
                    "id": "e1",
                    "session_id": "s1",
                    "event_type": "tool_call",
                    "data": {"tool_name": "search", "arguments": {"q": "test"}},
                    "event_metadata": {},
                    "timestamp": "2026-04-03T10:00:00Z",
                }
            ],
            1,
            EntityType.TOOL_NAME,
        ),
        # Multiple tool names
        (
            [
                {
                    "id": "e1",
                    "session_id": "s1",
                    "event_type": "tool_call",
                    "data": {"tool_name": "search"},
                    "event_metadata": {},
                    "timestamp": "2026-04-03T10:00:00Z",
                },
                {
                    "id": "e2",
                    "session_id": "s1",
                    "event_type": "tool_call",
                    "data": {"tool_name": "lookup"},
                    "event_metadata": {},
                    "timestamp": "2026-04-03T10:01:00Z",
                },
            ],
            2,
            EntityType.TOOL_NAME,
        ),
        # Error type extraction
        (
            [
                {
                    "id": "e1",
                    "session_id": "s1",
                    "event_type": "error",
                    "data": {"error_type": "RuntimeError", "error_message": "failed"},
                    "event_metadata": {},
                    "timestamp": "2026-04-03T10:00:00Z",
                }
            ],
            1,
            EntityType.ERROR_TYPE,
        ),
        # Model extraction
        (
            [
                {
                    "id": "e1",
                    "session_id": "s1",
                    "event_type": "llm_request",
                    "data": {"model": "gpt-4"},
                    "event_metadata": {},
                    "timestamp": "2026-04-03T10:00:00Z",
                }
            ],
            1,
            EntityType.MODEL,
        ),
    ],
)
def test_entity_extraction_basic(events, expected_count, expected_type):
    extractor = EntityExtractor()
    entities = extractor.extract_from_events(events)

    filtered = filter_entities_by_type(entities, expected_type)
    assert len(filtered) == expected_count


def test_entity_count_aggregation():
    extractor = EntityExtractor()
    events = [
        {
            "id": "e1",
            "session_id": "s1",
            "event_type": "tool_call",
            "data": {"tool_name": "search"},
            "event_metadata": {},
            "timestamp": "2026-04-03T10:00:00Z",
        },
        {
            "id": "e2",
            "session_id": "s1",
            "event_type": "tool_call",
            "data": {"tool_name": "search"},
            "event_metadata": {},
            "timestamp": "2026-04-03T10:01:00Z",
        },
        {
            "id": "e3",
            "session_id": "s1",
            "event_type": "tool_call",
            "data": {"tool_name": "lookup"},
            "event_metadata": {},
            "timestamp": "2026-04-03T10:02:00Z",
        },
    ]

    entities = extractor.extract_from_events(events)
    search_entity = entities.get(f"{EntityType.TOOL_NAME}:search")

    assert search_entity is not None
    assert search_entity.count == 2
    assert search_entity.value == "search"


def test_session_tracking():
    extractor = EntityExtractor()
    events = [
        {
            "id": "e1",
            "session_id": "s1",
            "event_type": "tool_call",
            "data": {"tool_name": "search"},
            "event_metadata": {},
            "timestamp": "2026-04-03T10:00:00Z",
        },
        {
            "id": "e2",
            "session_id": "s2",
            "event_type": "tool_call",
            "data": {"tool_name": "search"},
            "event_metadata": {},
            "timestamp": "2026-04-03T10:01:00Z",
        },
    ]

    entities = extractor.extract_from_events(events)
    search_entity = entities.get(f"{EntityType.TOOL_NAME}:search")

    assert search_entity is not None
    assert len(search_entity.session_ids) == 2
    assert "s1" in search_entity.session_ids
    assert "s2" in search_entity.session_ids


def test_rank_entities_by_count():
    entities = {
        "tool_name:search": Entity(entity_type=EntityType.TOOL_NAME, value="search", count=10),
        "tool_name:lookup": Entity(entity_type=EntityType.TOOL_NAME, value="lookup", count=5),
        "tool_name:write": Entity(entity_type=EntityType.TOOL_NAME, value="write", count=15),
    }

    ranked = rank_entities(entities, sort_by="count")

    assert ranked[0].value == "write"
    assert ranked[0].count == 15
    assert ranked[1].value == "search"
    assert ranked[2].value == "lookup"


def test_rank_entities_by_session_count():
    entities = {
        "tool_name:search": Entity(
            entity_type=EntityType.TOOL_NAME, value="search", count=10, session_ids={"s1", "s2"}
        ),
        "tool_name:lookup": Entity(
            entity_type=EntityType.TOOL_NAME, value="lookup", count=5, session_ids={"s1", "s2", "s3"}
        ),
    }

    ranked = rank_entities(entities, sort_by="session_count")

    assert ranked[0].value == "lookup"
    assert len(ranked[0].session_ids) == 3
    assert ranked[1].value == "search"


def test_get_top_entities_limit():
    entities = {
        f"tool_name:tool{i}": Entity(entity_type=EntityType.TOOL_NAME, value=f"tool{i}", count=i)
        for i in range(1, 21)
    }

    top_5 = get_top_entities(entities, entity_type=EntityType.TOOL_NAME, limit=5, sort_by="count")

    assert len(top_5) == 5
    assert top_5[0]["value"] == "tool20"  # Highest count


def test_get_top_entities_filter_by_type():
    entities = {
        "tool_name:search": Entity(entity_type=EntityType.TOOL_NAME, value="search", count=10),
        "error_type:RuntimeError": Entity(entity_type=EntityType.ERROR_TYPE, value="RuntimeError", count=5),
    }

    tools_only = get_top_entities(entities, entity_type=EntityType.TOOL_NAME, limit=10)

    assert len(tools_only) == 1
    assert tools_only[0]["value"] == "search"


def test_entity_to_dict():
    entity = Entity(
        entity_type=EntityType.TOOL_NAME,
        value="search",
        count=5,
        first_seen_at="2026-04-03T10:00:00Z",
        last_seen_at="2026-04-03T10:05:00Z",
        session_ids={"s1", "s2"},
        sample_event_ids=["e1", "e2", "e3"],
    )

    entity_dict = entity.to_dict()

    assert entity_dict["entity_type"] == EntityType.TOOL_NAME
    assert entity_dict["value"] == "search"
    assert entity_dict["count"] == 5
    assert entity_dict["session_count"] == 2
    assert len(entity_dict["sample_event_ids"]) <= 5


def test_policy_name_extraction():
    extractor = EntityExtractor()
    events = [
        {
            "id": "e1",
            "session_id": "s1",
            "event_type": "safety_check",
            "data": {"policy_name": "content_moderation", "outcome": "pass"},
            "event_metadata": {},
            "timestamp": "2026-04-03T10:00:00Z",
        }
    ]

    entities = extractor.extract_from_events(events)
    policy_entity = entities.get(f"{EntityType.POLICY_NAME}:content_moderation")

    assert policy_entity is not None
    assert policy_entity.value == "content_moderation"


def test_alert_type_extraction():
    extractor = EntityExtractor()
    events = [
        {
            "id": "e1",
            "session_id": "s1",
            "event_type": "behavior_alert",
            "data": {"alert_type": "looping", "severity": "high"},
            "event_metadata": {},
            "timestamp": "2026-04-03T10:00:00Z",
        }
    ]

    entities = extractor.extract_from_events(events)
    alert_entity = entities.get(f"{EntityType.ALERT_TYPE}:looping")

    assert alert_entity is not None
    assert alert_entity.value == "looping"


def test_violation_type_extraction():
    extractor = EntityExtractor()
    events = [
        {
            "id": "e1",
            "session_id": "s1",
            "event_type": "policy_violation",
            "data": {"violation_type": "prompt_injection", "severity": "critical"},
            "event_metadata": {},
            "timestamp": "2026-04-03T10:00:00Z",
        }
    ]

    entities = extractor.extract_from_events(events)
    violation_entity = entities.get(f"{EntityType.VIOLATION_TYPE}:prompt_injection")

    assert violation_entity is not None
    assert violation_entity.value == "prompt_injection"


def test_safe_alternative_extraction():
    extractor = EntityExtractor()
    events = [
        {
            "id": "e1",
            "session_id": "s1",
            "event_type": "refusal",
            "data": {"safe_alternative": "summarize", "blocked_action": "execute"},
            "event_metadata": {},
            "timestamp": "2026-04-03T10:00:00Z",
        }
    ]

    entities = extractor.extract_from_events(events)
    alt_entity = entities.get(f"{EntityType.SAFE_ALTERNATIVE}:summarize")

    assert alt_entity is not None
    assert alt_entity.value == "summarize"
