"""Add alert lifecycle fields to anomaly_alerts table.

Revision ID: 006_add_alert_lifecycle
Revises: 005_add_patterns
Create Date: 2026-04-04

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_add_alert_lifecycle"
down_revision: Union[str, None] = "005_add_patterns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Check if anomaly_alerts table exists
    if "anomaly_alerts" in inspector.get_table_names():
        # Get existing columns to check if they already exist
        existing_columns = {col["name"] for col in inspector.get_columns("anomaly_alerts")}

        # Add status column if it doesn't exist
        if "status" not in existing_columns:
            op.add_column(
                "anomaly_alerts",
                sa.Column("status", sa.String(32), nullable=False, server_default="active", index=True),
            )

        # Add acknowledged_at column if it doesn't exist
        if "acknowledged_at" not in existing_columns:
            op.add_column(
                "anomaly_alerts",
                sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
            )

        # Add resolved_at column if it doesn't exist
        if "resolved_at" not in existing_columns:
            op.add_column(
                "anomaly_alerts",
                sa.Column("resolved_at", sa.DateTime(), nullable=True),
            )

        # Add dismissed_at column if it doesn't exist
        if "dismissed_at" not in existing_columns:
            op.add_column(
                "anomaly_alerts",
                sa.Column("dismissed_at", sa.DateTime(), nullable=True),
            )

        # Add resolution_note column if it doesn't exist
        if "resolution_note" not in existing_columns:
            op.add_column(
                "anomaly_alerts",
                sa.Column("resolution_note", sa.Text(), nullable=True),
            )

        # Create composite index for status if it doesn't exist
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("anomaly_alerts")}
        if "ix_anomaly_alerts_tenant_id_status" not in existing_indexes:
            op.create_index(
                "ix_anomaly_alerts_tenant_id_status",
                "anomaly_alerts",
                ["tenant_id", "status"],
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Check if anomaly_alerts table exists before modifying
    if "anomaly_alerts" in inspector.get_table_names():
        # Drop index if it exists
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("anomaly_alerts")}
        if "ix_anomaly_alerts_tenant_id_status" in existing_indexes:
            op.drop_index("ix_anomaly_alerts_tenant_id_status", table_name="anomaly_alerts")

        # Get existing columns
        existing_columns = {col["name"] for col in inspector.get_columns("anomaly_alerts")}

        # Drop columns if they exist
        if "resolution_note" in existing_columns:
            op.drop_column("anomaly_alerts", "resolution_note")
        if "dismissed_at" in existing_columns:
            op.drop_column("anomaly_alerts", "dismissed_at")
        if "resolved_at" in existing_columns:
            op.drop_column("anomaly_alerts", "resolved_at")
        if "acknowledged_at" in existing_columns:
            op.drop_column("anomaly_alerts", "acknowledged_at")
        if "status" in existing_columns:
            op.drop_column("anomaly_alerts", "status")
