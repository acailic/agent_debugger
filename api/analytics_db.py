"""Analytics database operations for local user analytics.

This module provides SQLite-based storage for tracking user debugging efficiency
metrics. It uses a separate analytics.db file from the main database, with
fire-and-forget writes that don't block callers.

All operations are synchronous since analytics is local-only and single-user.
Errors are logged but don't propagate to avoid impacting the main application.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from storage.analytics_migrations import ensure_analytics_schema

logger = logging.getLogger("agent_debugger.analytics")

# Mapping from event types to aggregate column names
EVENT_TO_AGGREGATE_COLUMN: dict[str, str] = {
    "session_created": "sessions_created",
    "why_button_clicked": "why_button_clicks",
    "failure_matched": "failures_matched",
    "replay_started": "replays_started",
    "replay_highlights_used": "replay_highlights_used",
    "behavior_alert_viewed": "behavior_alerts_viewed",
    "nl_query_made": "nl_queries_made",
    "search_performed": "searches_performed",
}


def get_analytics_db_path() -> Path:
    """Return the path to the analytics.db file.

    The analytics database is stored in the same directory as the main
    agent_debugger.db database (./data/ by default).

    Returns:
        Path to analytics.db
    """
    # Use same directory as main database
    # Default is ./data/agent_debugger.db, so analytics goes in ./data/analytics.db
    return Path.cwd() / "data" / "analytics.db"


def init_analytics_db() -> None:
    """Initialize the analytics database, creating tables if needed.

    This is safe to call multiple times - it only creates missing tables.
    Errors are logged but not raised to avoid startup failures.
    """
    try:
        db_path = get_analytics_db_path()
        ensure_analytics_schema(db_path)
    except Exception:
        logger.warning("Failed to initialize analytics database", exc_info=True)


def record_event(
    event_type: str,
    session_id: str | None = None,
    agent_name: str | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    """Record an analytics event and update daily aggregates.

    This is a fire-and-forget operation - errors are logged but not raised.
    The event is inserted into analytics_events and the corresponding daily
    aggregate counter is incremented.

    Args:
        event_type: Type of event (e.g., "session_created", "why_button_clicked")
        session_id: Optional session ID associated with the event
        agent_name: Optional agent name associated with the event
        properties: Optional dict of additional properties (stored as JSON)
    """
    try:
        db_path = get_analytics_db_path()

        # Ensure schema exists
        ensure_analytics_schema(db_path)

        # Get today's date in YYYY-MM-DD format
        today = datetime.now().strftime("%Y-%m-%d")

        # Serialize properties to JSON
        properties_json = json.dumps(properties) if properties else None

        with sqlite3.connect(str(db_path)) as conn:
            # Insert the event
            conn.execute(
                """
                INSERT INTO analytics_events (event_type, session_id, agent_name, properties)
                VALUES (?, ?, ?, ?)
                """,
                (event_type, session_id, agent_name, properties_json),
            )

            # Update daily aggregate
            aggregate_column = EVENT_TO_AGGREGATE_COLUMN.get(event_type)
            if aggregate_column:
                # Use INSERT OR REPLACE pattern for upsert
                # First try to insert the row for today if it doesn't exist
                conn.execute(
                    """
                    INSERT OR IGNORE INTO daily_aggregates (date)
                    VALUES (?)
                    """,
                    (today,),
                )
                # Then increment the appropriate counter
                conn.execute(
                    f"""
                    UPDATE daily_aggregates
                    SET {aggregate_column} = {aggregate_column} + 1
                    WHERE date = ?
                    """,
                    (today,),
                )

            conn.commit()

    except sqlite3.Error:
        logger.warning("Failed to record analytics event: %s", event_type, exc_info=True)
    except Exception:
        logger.warning("Unexpected error recording analytics event: %s", event_type, exc_info=True)


def get_aggregates(days: int = 7) -> dict[str, int]:
    """Get aggregated analytics totals for the last N days.

    Args:
        days: Number of days to include (default 7)

    Returns:
        Dict with summed totals for each metric over the period:
        - sessions_created
        - why_button_clicks
        - failures_matched
        - replays_started
        - replay_highlights_used
        - behavior_alerts_viewed
        - nl_queries_made
        - searches_performed
    """
    defaults = {
        "sessions_created": 0,
        "why_button_clicks": 0,
        "failures_matched": 0,
        "replays_started": 0,
        "replay_highlights_used": 0,
        "behavior_alerts_viewed": 0,
        "nl_queries_made": 0,
        "searches_performed": 0,
    }

    try:
        db_path = get_analytics_db_path()

        if not db_path.exists():
            return defaults

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT
                    COALESCE(SUM(sessions_created), 0) as sessions_created,
                    COALESCE(SUM(why_button_clicks), 0) as why_button_clicks,
                    COALESCE(SUM(failures_matched), 0) as failures_matched,
                    COALESCE(SUM(replays_started), 0) as replays_started,
                    COALESCE(SUM(replay_highlights_used), 0) as replay_highlights_used,
                    COALESCE(SUM(behavior_alerts_viewed), 0) as behavior_alerts_viewed,
                    COALESCE(SUM(nl_queries_made), 0) as nl_queries_made,
                    COALESCE(SUM(searches_performed), 0) as searches_performed
                FROM daily_aggregates
                WHERE date >= ?
                """,
                (cutoff_date,),
            )
            row = cursor.fetchone()

            if row:
                return {key: row[key] for key in defaults}
            return defaults

    except sqlite3.Error:
        logger.warning("Failed to get analytics aggregates", exc_info=True)
        return defaults
    except Exception:
        logger.warning("Unexpected error getting analytics aggregates", exc_info=True)
        return defaults


def get_daily_breakdown(days: int = 14) -> list[dict[str, Any]]:
    """Get per-day analytics for sparkline visualization.

    Args:
        days: Number of days to include (default 14)

    Returns:
        List of dicts, one per day, with keys:
        - date: YYYY-MM-DD string
        - sessions_created: int
        - why_button_clicks: int
        - failures_matched: int
        - replays_started: int
        - replay_highlights_used: int
        - behavior_alerts_viewed: int
        - nl_queries_made: int
        - searches_performed: int

        Days with no data are filled with zeros.
    """
    empty_day = {
        "sessions_created": 0,
        "why_button_clicks": 0,
        "failures_matched": 0,
        "replays_started": 0,
        "replay_highlights_used": 0,
        "behavior_alerts_viewed": 0,
        "nl_queries_made": 0,
        "searches_performed": 0,
    }

    try:
        db_path = get_analytics_db_path()

        # Generate list of dates for the period
        today = datetime.now()
        date_range = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]

        if not db_path.exists():
            return [{"date": d, **empty_day} for d in reversed(date_range)]

        cutoff_date = date_range[-1]

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row

            # Fetch all aggregates in the range
            cursor = conn.execute(
                """
                SELECT * FROM daily_aggregates
                WHERE date >= ?
                ORDER BY date ASC
                """,
                (cutoff_date,),
            )
            rows = cursor.fetchall()

            # Build a map of date -> row data
            data_by_date = {row["date"]: dict(row) for row in rows}

            # Build result, filling missing days with zeros
            result = []
            for date in reversed(date_range):  # Oldest first
                if date in data_by_date:
                    result.append({"date": date, **data_by_date[date]})
                else:
                    result.append({"date": date, **empty_day})

            return result

    except sqlite3.Error:
        logger.warning("Failed to get daily analytics breakdown", exc_info=True)
        # Return empty structure
        today = datetime.now()
        date_range = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        return [{"date": d, **empty_day} for d in reversed(date_range)]
    except Exception:
        logger.warning("Unexpected error getting daily analytics breakdown", exc_info=True)
        today = datetime.now()
        date_range = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        return [{"date": d, **empty_day} for d in reversed(date_range)]
