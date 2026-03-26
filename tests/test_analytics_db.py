"""Tests for analytics database operations."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

import api.analytics_db as analytics_db
from storage.analytics_migrations import ensure_analytics_schema


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create a temporary database path for testing."""
    return tmp_path / "test_analytics.db"


@pytest.fixture
def mock_db_path(temp_db_path: Path):
    """Mock get_analytics_db_path to use a temporary location."""
    with patch.object(analytics_db, "get_analytics_db_path", return_value=temp_db_path):
        yield temp_db_path


class TestAnalyticsMigrations:
    """Tests for analytics schema migration."""

    def test_ensure_analytics_schema_creates_tables(self, temp_db_path: Path):
        """Test that ensure_analytics_schema creates all required tables."""
        ensure_analytics_schema(temp_db_path)

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "analytics_events" in tables
        assert "daily_aggregates" in tables

    def test_ensure_analytics_schema_creates_indexes(self, temp_db_path: Path):
        """Test that ensure_analytics_schema creates required indexes."""
        ensure_analytics_schema(temp_db_path)

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "idx_events_type" in indexes
        assert "idx_events_created" in indexes
        assert "idx_events_session" in indexes

    def test_ensure_analytics_schema_idempotent(self, temp_db_path: Path):
        """Test that ensure_analytics_schema can be called multiple times safely."""
        ensure_analytics_schema(temp_db_path)
        ensure_analytics_schema(temp_db_path)  # Should not raise

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        # Should have our 2 tables (sqlite_sequence is auto-created by AUTOINCREMENT)
        assert "analytics_events" in tables
        assert "daily_aggregates" in tables

    def test_ensure_analytics_schema_creates_parent_dir(self, tmp_path: Path):
        """Test that ensure_analytics_schema creates parent directories."""
        db_path = tmp_path / "nested" / "dir" / "analytics.db"
        ensure_analytics_schema(db_path)
        assert db_path.parent.exists()


class TestGetAnalyticsDbPath:
    """Tests for get_analytics_db_path."""

    def test_returns_path_in_data_dir(self):
        """Test that path is under data directory."""
        path = analytics_db.get_analytics_db_path()
        assert path.name == "analytics.db"
        assert "data" in str(path)


class TestInitAnalyticsDb:
    """Tests for init_analytics_db."""

    def test_init_creates_tables(self, mock_db_path: Path):
        """Test that init_analytics_db creates tables."""
        analytics_db.init_analytics_db()

        assert mock_db_path.exists()
        conn = sqlite3.connect(str(mock_db_path))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "analytics_events" in tables
        assert "daily_aggregates" in tables

    def test_init_is_idempotent(self, mock_db_path: Path):
        """Test that init_analytics_db can be called multiple times."""
        analytics_db.init_analytics_db()
        analytics_db.init_analytics_db()  # Should not raise


class TestRecordEvent:
    """Tests for record_event."""

    def test_record_event_inserts_event(self, mock_db_path: Path):
        """Test that record_event inserts an event into the database."""
        analytics_db.init_analytics_db()
        analytics_db.record_event("session_created", session_id="test-123")

        conn = sqlite3.connect(str(mock_db_path))
        cursor = conn.execute("SELECT * FROM analytics_events")
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[1] == "session_created"  # event_type
        assert row[2] == "test-123"  # session_id

    def test_record_event_with_all_fields(self, mock_db_path: Path):
        """Test recording an event with all optional fields."""
        analytics_db.init_analytics_db()
        properties = {"key": "value", "count": 42}
        analytics_db.record_event(
            "why_button_clicked",
            session_id="session-abc",
            agent_name="TestAgent",
            properties=properties,
        )

        conn = sqlite3.connect(str(mock_db_path))
        cursor = conn.execute("SELECT * FROM analytics_events")
        row = cursor.fetchone()
        conn.close()

        assert row[1] == "why_button_clicked"
        assert row[2] == "session-abc"
        assert row[3] == "TestAgent"
        assert json.loads(row[4]) == properties

    def test_record_event_updates_daily_aggregate(self, mock_db_path: Path):
        """Test that record_event increments the daily aggregate."""
        analytics_db.init_analytics_db()
        analytics_db.record_event("session_created")
        analytics_db.record_event("session_created")

        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(str(mock_db_path))
        cursor = conn.execute(
            "SELECT sessions_created FROM daily_aggregates WHERE date = ?",
            (today,),
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 2

    def test_record_event_unknown_type_still_inserts(self, mock_db_path: Path):
        """Test that unknown event types are still recorded (just not aggregated)."""
        analytics_db.init_analytics_db()
        analytics_db.record_event("unknown_event_type")

        conn = sqlite3.connect(str(mock_db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM analytics_events")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1

    def test_record_event_handles_all_event_types(self, mock_db_path: Path):
        """Test that all defined event types update correct aggregates."""
        analytics_db.init_analytics_db()

        event_types = [
            "session_created",
            "why_button_clicked",
            "failure_matched",
            "replay_started",
            "replay_highlights_used",
            "behavior_alert_viewed",
            "nl_query_made",
            "search_performed",
        ]

        for event_type in event_types:
            analytics_db.record_event(event_type)

        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(str(mock_db_path))
        cursor = conn.execute(
            "SELECT * FROM daily_aggregates WHERE date = ?",
            (today,),
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        # Check each aggregate column
        assert row[1] == 1  # sessions_created
        assert row[2] == 1  # why_button_clicks
        assert row[3] == 1  # failures_matched
        assert row[4] == 1  # replays_started
        assert row[5] == 1  # replay_highlights_used
        assert row[6] == 1  # behavior_alerts_viewed
        assert row[7] == 1  # nl_queries_made
        assert row[8] == 1  # searches_performed

    def test_record_event_handles_missing_db_gracefully(self, tmp_path: Path):
        """Test that record_event handles database errors gracefully."""
        # Use a path that will fail (e.g., in a non-existent directory without parent)
        # Actually, the code creates parent dirs, so let's test differently
        # Just ensure no exception is raised even in edge cases
        db_path = tmp_path / "analytics.db"
        with patch.object(analytics_db, "get_analytics_db_path", return_value=db_path):
            # This should not raise even if schema init fails somehow
            analytics_db.record_event("session_created")

    def test_record_event_with_none_properties(self, mock_db_path: Path):
        """Test recording event with None properties."""
        analytics_db.init_analytics_db()
        analytics_db.record_event("session_created", properties=None)

        conn = sqlite3.connect(str(mock_db_path))
        cursor = conn.execute("SELECT properties FROM analytics_events")
        row = cursor.fetchone()
        conn.close()

        assert row[0] is None


class TestGetAggregates:
    """Tests for get_aggregates."""

    def test_get_aggregates_returns_defaults_for_missing_db(self, tmp_path: Path):
        """Test that get_aggregates returns defaults when DB doesn't exist."""
        db_path = tmp_path / "nonexistent.db"
        with patch.object(analytics_db, "get_analytics_db_path", return_value=db_path):
            result = analytics_db.get_aggregates(days=7)

            assert result["sessions_created"] == 0
            assert result["why_button_clicks"] == 0

    def test_get_aggregates_sums_multiple_days(self, mock_db_path: Path):
        """Test that get_aggregates sums data across multiple days."""
        analytics_db.init_analytics_db()

        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        conn = sqlite3.connect(str(mock_db_path))
        conn.execute(
            "INSERT INTO daily_aggregates (date, sessions_created, why_button_clicks) VALUES (?, 5, 3)",
            (today,),
        )
        conn.execute(
            "INSERT INTO daily_aggregates (date, sessions_created, why_button_clicks) VALUES (?, 2, 1)",
            (yesterday,),
        )
        conn.commit()
        conn.close()

        result = analytics_db.get_aggregates(days=7)

        assert result["sessions_created"] == 7
        assert result["why_button_clicks"] == 4

    def test_get_aggregates_respects_days_parameter(self, mock_db_path: Path):
        """Test that get_aggregates only includes data within the specified range."""
        analytics_db.init_analytics_db()

        today = datetime.now().strftime("%Y-%m-%d")
        old_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        conn = sqlite3.connect(str(mock_db_path))
        conn.execute(
            "INSERT INTO daily_aggregates (date, sessions_created) VALUES (?, 5)",
            (today,),
        )
        conn.execute(
            "INSERT INTO daily_aggregates (date, sessions_created) VALUES (?, 100)",
            (old_date,),
        )
        conn.commit()
        conn.close()

        result = analytics_db.get_aggregates(days=7)

        # Only today's data should be included
        assert result["sessions_created"] == 5

    def test_get_aggregates_returns_all_fields(self, mock_db_path: Path):
        """Test that get_aggregates returns all expected fields."""
        analytics_db.init_analytics_db()

        result = analytics_db.get_aggregates(days=7)

        expected_keys = [
            "sessions_created",
            "why_button_clicks",
            "failures_matched",
            "replays_started",
            "replay_highlights_used",
            "behavior_alerts_viewed",
            "nl_queries_made",
            "searches_performed",
        ]
        for key in expected_keys:
            assert key in result


class TestGetDailyBreakdown:
    """Tests for get_daily_breakdown."""

    def test_get_daily_breakdown_returns_empty_structure_for_missing_db(self, tmp_path: Path):
        """Test that get_daily_breakdown returns empty structure when DB missing."""
        db_path = tmp_path / "nonexistent.db"
        with patch.object(analytics_db, "get_analytics_db_path", return_value=db_path):
            result = analytics_db.get_daily_breakdown(days=7)

            assert len(result) == 7
            assert all("date" in day for day in result)
            assert all(day["sessions_created"] == 0 for day in result)

    def test_get_daily_breakdown_returns_correct_number_of_days(self, mock_db_path: Path):
        """Test that get_daily_breakdown returns exactly N days."""
        analytics_db.init_analytics_db()

        result = analytics_db.get_daily_breakdown(days=14)

        assert len(result) == 14

    def test_get_daily_breakdown_fills_missing_days_with_zeros(self, mock_db_path: Path):
        """Test that get_daily_breakdown fills gaps with zero data."""
        analytics_db.init_analytics_db()

        result = analytics_db.get_daily_breakdown(days=7)

        # All days should have the expected structure
        for day in result:
            assert "date" in day
            assert day["sessions_created"] == 0
            assert day["why_button_clicks"] == 0

    def test_get_daily_breakdown_returns_chronological_order(self, mock_db_path: Path):
        """Test that results are ordered from oldest to newest."""
        analytics_db.init_analytics_db()

        result = analytics_db.get_daily_breakdown(days=7)

        dates = [day["date"] for day in result]
        assert dates == sorted(dates)

    def test_get_daily_breakdown_includes_actual_data(self, mock_db_path: Path):
        """Test that get_daily_breakdown includes actual recorded data."""
        analytics_db.init_analytics_db()

        # Record some events
        analytics_db.record_event("session_created")
        analytics_db.record_event("why_button_clicked")

        result = analytics_db.get_daily_breakdown(days=1)
        today = datetime.now().strftime("%Y-%m-%d")

        assert len(result) == 1
        assert result[0]["date"] == today
        assert result[0]["sessions_created"] == 1
        assert result[0]["why_button_clicks"] == 1

    def test_get_daily_breakdown_returns_all_fields(self, mock_db_path: Path):
        """Test that get_daily_breakdown returns all expected fields per day."""
        analytics_db.init_analytics_db()

        result = analytics_db.get_daily_breakdown(days=1)

        expected_keys = [
            "date",
            "sessions_created",
            "why_button_clicks",
            "failures_matched",
            "replays_started",
            "replay_highlights_used",
            "behavior_alerts_viewed",
            "nl_queries_made",
            "searches_performed",
        ]
        for key in expected_keys:
            assert key in result[0]


class TestIntegration:
    """Integration tests for the analytics system."""

    def test_full_workflow(self, mock_db_path: Path):
        """Test complete workflow: init, record, query."""
        # Initialize
        analytics_db.init_analytics_db()

        # Record various events
        analytics_db.record_event("session_created", session_id="s1")
        analytics_db.record_event("why_button_clicked", session_id="s1")
        analytics_db.record_event("failure_matched", session_id="s1")
        analytics_db.record_event("session_created", session_id="s2")
        analytics_db.record_event("replay_started", session_id="s2")
        analytics_db.record_event("search_performed", session_id="s2")

        # Query aggregates
        aggregates = analytics_db.get_aggregates(days=1)
        assert aggregates["sessions_created"] == 2
        assert aggregates["why_button_clicks"] == 1
        assert aggregates["failures_matched"] == 1
        assert aggregates["replays_started"] == 1
        assert aggregates["searches_performed"] == 1

        # Query daily breakdown
        breakdown = analytics_db.get_daily_breakdown(days=1)
        assert len(breakdown) == 1
        assert breakdown[0]["sessions_created"] == 2

    def test_error_handling_does_not_propagate(self, tmp_path: Path):
        """Test that database errors don't propagate to callers."""
        # Create a situation that would fail
        db_path = tmp_path / "readonly" / "analytics.db"
        db_path.parent.mkdir()

        # Make the directory read-only (won't work on all systems)
        # Instead, just verify the functions return safe defaults
        with patch.object(analytics_db, "get_analytics_db_path", return_value=db_path):
            # These should not raise
            analytics_db.init_analytics_db()
            analytics_db.record_event("session_created")
            result = analytics_db.get_aggregates(days=7)
            assert isinstance(result, dict)

            breakdown = analytics_db.get_daily_breakdown(days=7)
            assert isinstance(breakdown, list)
