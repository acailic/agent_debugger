"""Add indexes for alert and analytics query optimization.

Revision ID: 008_add_alert_indexes
Revises: 007_add_alert_policies
Create Date: 2026-04-04

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_add_alert_indexes"
down_revision: Union[str, None] = "007_add_alert_policies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Get existing indexes to avoid duplicates
    def index_exists(table_name: str, index_name: str) -> bool:
        existing_indexes = inspector.get_indexes(table_name)
        return any(idx["name"] == index_name for idx in existing_indexes)

    # Create indexes for anomaly_alerts table
    if not index_exists("anomaly_alerts", "ix_anomaly_alerts_created_at"):
        op.create_index("ix_anomaly_alerts_created_at", "anomaly_alerts", ["created_at"])

    if not index_exists("anomaly_alerts", "ix_anomaly_alerts_severity"):
        op.create_index("ix_anomaly_alerts_severity", "anomaly_alerts", ["severity"])

    if not index_exists("anomaly_alerts", "ix_anomaly_alerts_alert_type"):
        op.create_index("ix_anomaly_alerts_alert_type", "anomaly_alerts", ["alert_type"])

    if not index_exists("anomaly_alerts", "ix_anomaly_alerts_session_id"):
        op.create_index("ix_anomaly_alerts_session_id", "anomaly_alerts", ["session_id"])

    # Status column was added in migration 006, now index it
    if not index_exists("anomaly_alerts", "ix_anomaly_alerts_status"):
        op.create_index("ix_anomaly_alerts_status", "anomaly_alerts", ["status"])

    # Create indexes for patterns table (individual columns for additional query patterns)
    if not index_exists("patterns", "ix_patterns_status"):
        op.create_index("ix_patterns_status", "patterns", ["status"])

    if not index_exists("patterns", "ix_patterns_pattern_type"):
        op.create_index("ix_patterns_pattern_type", "patterns", ["pattern_type"])

    # Create indexes for sessions table
    if not index_exists("sessions", "ix_sessions_started_at"):
        op.create_index("ix_sessions_started_at", "sessions", ["started_at"])

    if not index_exists("sessions", "ix_sessions_agent_name"):
        op.create_index("ix_sessions_agent_name", "sessions", ["agent_name"])

    # Create composite index for events table (session_id, created_at)
    # This optimizes queries that filter by session and order by timestamp
    if not index_exists("events", "ix_events_session_id_created_at"):
        op.create_index("ix_events_session_id_created_at", "events", ["session_id", "timestamp"])

    # Create index for events.event_type (if not exists)
    if not index_exists("events", "ix_events_event_type"):
        op.create_index("ix_events_event_type", "events", ["event_type"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    def index_exists(table_name: str, index_name: str) -> bool:
        existing_indexes = inspector.get_indexes(table_name)
        return any(idx["name"] == index_name for idx in existing_indexes)

    # Drop indexes in reverse order
    if index_exists("events", "ix_events_event_type"):
        op.drop_index("ix_events_event_type", table_name="events")

    if index_exists("events", "ix_events_session_id_created_at"):
        op.drop_index("ix_events_session_id_created_at", table_name="events")

    if index_exists("sessions", "ix_sessions_agent_name"):
        op.drop_index("ix_sessions_agent_name", table_name="sessions")

    if index_exists("sessions", "ix_sessions_created_at"):
        op.drop_index("ix_sessions_created_at", table_name="sessions")

    if index_exists("patterns", "ix_patterns_pattern_type"):
        op.drop_index("ix_patterns_pattern_type", table_name="patterns")

    if index_exists("patterns", "ix_patterns_status"):
        op.drop_index("ix_patterns_status", table_name="patterns")

    if index_exists("anomaly_alerts", "ix_anomaly_alerts_session_id"):
        op.drop_index("ix_anomaly_alerts_session_id", table_name="anomaly_alerts")

    if index_exists("anomaly_alerts", "ix_anomaly_alerts_alert_type"):
        op.drop_index("ix_anomaly_alerts_alert_type", table_name="anomaly_alerts")

    if index_exists("anomaly_alerts", "ix_anomaly_alerts_severity"):
        op.drop_index("ix_anomaly_alerts_severity", table_name="anomaly_alerts")

    if index_exists("anomaly_alerts", "ix_anomaly_alerts_status"):
        op.drop_index("ix_anomaly_alerts_status", table_name="anomaly_alerts")

    if index_exists("anomaly_alerts", "ix_anomaly_alerts_created_at"):
        op.drop_index("ix_anomaly_alerts_created_at", table_name="anomaly_alerts")
