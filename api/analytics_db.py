"""Analytics database operations facade for local user analytics.

This module provides a facade over the storage layer AnalyticsRepository,
maintaining backward compatibility with existing imports. All database
operations are delegated to the proper repository class in storage/.

All operations are synchronous since analytics is local-only and single-user.
Errors are logged but don't propagate to avoid impacting the main application.

NOTE: Analytics data is intentionally NOT tenant-isolated.  This module
tracks local-only usage patterns (button clicks, search queries) for a
single developer's own dashboard.  Tenant-scoped analytics should use a
separate collection path when cloud multi-tenancy is implemented.
"""

from __future__ import annotations

from pathlib import Path

from storage.repositories.analytics_repo import AnalyticsRepository

# Singleton repository instance
_repository: AnalyticsRepository | None = None
# Override path for testing
_test_db_path: Path | None = None


def _get_repository() -> AnalyticsRepository:
    """Get or create the singleton analytics repository instance."""
    global _repository
    if _repository is None:
        if _test_db_path is not None:
            _repository = AnalyticsRepository(db_path=_test_db_path)
        else:
            _repository = AnalyticsRepository()
    return _repository


def get_analytics_db_path() -> Path:
    """Return the path to the analytics.db file.

    The analytics database is stored in the same directory as the main
    agent_debugger.db database (./data/ by default).

    Returns:
        Path to analytics.db
    """
    if _test_db_path is not None:
        return _test_db_path
    return _get_repository().db_path


def _set_test_db_path(path: Path) -> None:
    """Set a test database path (for testing only).

    This allows tests to override the database location without
    affecting the singleton repository behavior.
    """
    global _test_db_path, _repository
    _test_db_path = path
    _repository = None  # Reset to use new path


def init_analytics_db() -> None:
    """Initialize the analytics database, creating tables if needed.

    This is safe to call multiple times - it only creates missing tables.
    Errors are logged but not raised to avoid startup failures.
    """
    _get_repository().ensure_schema()


def record_event(
    event_type: str,
    session_id: str | None = None,
    agent_name: str | None = None,
    properties: dict[str, any] | None = None,
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
    _get_repository().record_event(
        event_type=event_type,
        session_id=session_id,
        agent_name=agent_name,
        properties=properties,
    )


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
    return _get_repository().get_aggregates(days=days)


def get_daily_breakdown(days: int = 14) -> list[dict[str, any]]:
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
    return _get_repository().get_daily_breakdown(days=days)
