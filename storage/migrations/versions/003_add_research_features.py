"""Add research features tables and retention columns.

Revision ID: 003_add_research_features
Revises: 002_add_session_replay_value
Create Date: 2026-03-24

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_research_features"
down_revision: Union[str, None] = "002_add_session_replay_value"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add retention columns to sessions table
    op.add_column(
        "sessions",
        sa.Column("retention_tier", sa.String(16), nullable=False, server_default="downsampled"),
    )
    op.create_index("ix_sessions_retention_tier", "sessions", ["retention_tier"])

    op.add_column(
        "sessions",
        sa.Column("failure_fingerprint_primary", sa.String(255), nullable=True),
    )
    op.create_index("ix_sessions_failure_fingerprint_primary", "sessions", ["failure_fingerprint_primary"])

    op.add_column(
        "sessions",
        sa.Column("cluster_representative", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.create_index("ix_sessions_cluster_representative", "sessions", ["cluster_representative"])

    op.add_column(
        "sessions",
        sa.Column("cluster_id", sa.String(36), nullable=True),
    )

    # Create failure_clusters table
    op.create_table(
        "failure_clusters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="local"),
        sa.Column("fingerprint", sa.String(255)),
        sa.Column("first_seen", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_seen", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("session_count", sa.Integer(), server_default="1"),
        sa.Column("event_count", sa.Integer(), server_default="0"),
        sa.Column("representative_session_id", sa.String(36), sa.ForeignKey("sessions.id")),
        sa.Column("representative_event_id", sa.String(36)),
        sa.Column("sample_failure_mode", sa.String(64)),
        sa.Column("sample_symptom", sa.String(512)),
        sa.Column("avg_severity", sa.Float(), server_default="0.0"),
    )
    op.create_index("ix_failure_clusters_tenant_id", "failure_clusters", ["tenant_id"])
    op.create_index("ix_failure_clusters_fingerprint", "failure_clusters", ["fingerprint"])

    # Create anomaly_alerts table
    op.create_table(
        "anomaly_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="local"),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id")),
        sa.Column("alert_type", sa.String(64)),
        sa.Column("severity", sa.Float()),
        sa.Column("signal", sa.Text()),
        sa.Column("event_ids", sa.JSON()),
        sa.Column("detection_source", sa.String(32)),
        sa.Column("detection_config", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_anomaly_alerts_tenant_id", "anomaly_alerts", ["tenant_id"])
    op.create_index("ix_anomaly_alerts_session_id", "anomaly_alerts", ["session_id"])
    op.create_index("ix_anomaly_alerts_alert_type", "anomaly_alerts", ["alert_type"])


def downgrade() -> None:
    # Drop anomaly_alerts table
    op.drop_index("ix_anomaly_alerts_alert_type", table_name="anomaly_alerts")
    op.drop_index("ix_anomaly_alerts_session_id", table_name="anomaly_alerts")
    op.drop_index("ix_anomaly_alerts_tenant_id", table_name="anomaly_alerts")
    op.drop_table("anomaly_alerts")

    # Drop failure_clusters table
    op.drop_index("ix_failure_clusters_fingerprint", table_name="failure_clusters")
    op.drop_index("ix_failure_clusters_tenant_id", table_name="failure_clusters")
    op.drop_table("failure_clusters")

    # Drop retention columns from sessions
    op.drop_column("sessions", "cluster_id")
    op.drop_index("ix_sessions_cluster_representative", table_name="sessions")
    op.drop_column("sessions", "cluster_representative")
    op.drop_index("ix_sessions_failure_fingerprint_primary", table_name="sessions")
    op.drop_column("sessions", "failure_fingerprint_primary")
    op.drop_index("ix_sessions_retention_tier", table_name="sessions")
    op.drop_column("sessions", "retention_tier")
