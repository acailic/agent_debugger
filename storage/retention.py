"""Retention policy enforcement."""
from __future__ import annotations

import datetime
from typing import Any


RETENTION_DAYS = {
    "free": 7,
    "developer": 30,
    "team": 90,
    "business": 365,
}


def get_retention_days(plan: str) -> int:
    return RETENTION_DAYS.get(plan, 7)


def find_expired_sessions(
    sessions: list[dict[str, Any]],
    now: datetime.datetime | None = None,
) -> list[dict[str, Any]]:
    now = now or datetime.datetime.now(datetime.UTC)
    expired = []
    for s in sessions:
        plan = s.get("plan", "free")
        max_age = datetime.timedelta(days=get_retention_days(plan))
        if now - s["started_at"] > max_age:
            expired.append(s)
    return expired