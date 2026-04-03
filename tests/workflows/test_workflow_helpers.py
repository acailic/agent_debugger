from __future__ import annotations

from copy import deepcopy

from tests.fixtures.workflow_helpers import cassette_events


def test_cassette_events_does_not_mutate_interactions():
    interactions = [
        {
            "type": "tool_call",
            "name": "search",
            "tool_name": "web.search",
            "arguments": {"q": "Belgrade"},
        }
    ]
    original = deepcopy(interactions)

    events = cassette_events(interactions, session_id="session-1")

    assert interactions == original
    assert len(events) == 1
    assert events[0].session_id == "session-1"
