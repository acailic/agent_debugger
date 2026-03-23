import datetime
import os
import sys

# Add the storage directory to the path to import retention directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'storage'))
from retention import find_expired_sessions, get_retention_days


def test_retention_days_by_plan():
    assert get_retention_days("free") == 7        # Local/free cloud tier
    assert get_retention_days("developer") == 30   # ADR-008
    assert get_retention_days("team") == 90        # ADR-008
    assert get_retention_days("business") == 365   # ADR-008


def test_find_expired_sessions():
    """Sessions older than retention period should be flagged."""
    now = datetime.datetime.now(datetime.UTC)
    sessions = [
        {"id": "old", "started_at": now - datetime.timedelta(days=40), "plan": "developer"},
        {"id": "new", "started_at": now - datetime.timedelta(days=5), "plan": "developer"},
    ]
    expired = find_expired_sessions(sessions, now)
    assert [s["id"] for s in expired] == ["old"]


def test_unknown_plan_uses_default():
    assert get_retention_days("enterprise") == 7  # Falls back to default
