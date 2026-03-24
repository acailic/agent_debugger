"""Analytics database schema setup for local user analytics.

This module provides schema initialization for the analytics.db SQLite database,
which tracks user debugging efficiency metrics locally. This is separate from
the main agent_debugger.db database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

ANALYTICS_SCHEMA = """
-- Event log for user analytics
CREATE TABLE IF NOT EXISTS analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    session_id TEXT,
    agent_name TEXT,
    properties TEXT,  -- JSON blob
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_events_type ON analytics_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created ON analytics_events(created_at);
CREATE INDEX IF NOT EXISTS idx_events_session ON analytics_events(session_id);

-- Daily aggregates for dashboard metrics
CREATE TABLE IF NOT EXISTS daily_aggregates (
    date TEXT NOT NULL PRIMARY KEY,
    sessions_created INTEGER DEFAULT 0,
    why_button_clicks INTEGER DEFAULT 0,
    failures_matched INTEGER DEFAULT 0,
    replays_started INTEGER DEFAULT 0,
    replay_highlights_used INTEGER DEFAULT 0,
    behavior_alerts_viewed INTEGER DEFAULT 0,
    nl_queries_made INTEGER DEFAULT 0,
    searches_performed INTEGER DEFAULT 0
);
"""


def ensure_analytics_schema(db_path: Path) -> None:
    """Create analytics tables if they do not exist.

    Args:
        db_path: Path to the analytics.db file
    """
    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(ANALYTICS_SCHEMA)
        conn.commit()
    finally:
        conn.close()
