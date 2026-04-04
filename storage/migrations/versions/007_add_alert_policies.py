"""Add alert_policies table for configurable alert thresholds.

Revision ID: 007_add_alert_policies
Revises: 006_add_alert_lifecycle
Create Date: 2026-04-04

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_add_alert_policies"
down_revision: Union[str, None] = "006_add_alert_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Check if alert_policies table already exists
    if "alert_policies" not in inspector.get_table_names():
        op.create_table(
            "alert_policies",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("tenant_id", sa.String(64), nullable=False, index=True, server_default="local"),
            sa.Column("agent_name", sa.String(255), nullable=True, index=True),
            sa.Column("alert_type", sa.String(64), nullable=False, index=True),
            sa.Column("threshold_value", sa.Float(), nullable=False),
            sa.Column("severity_threshold", sa.String(16), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )

        # Create composite indexes for common query patterns
        op.create_index("ix_alert_policies_tenant_agent", "alert_policies", ["tenant_id", "agent_name"])
        op.create_index("ix_alert_policies_tenant_type", "alert_policies", ["tenant_id", "alert_type"])
        op.create_index(
            "ix_alert_policies_tenant_agent_type", "alert_policies", ["tenant_id", "agent_name", "alert_type"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Check if alert_policies table exists before dropping (idempotency)
    if "alert_policies" in inspector.get_table_names():
        op.drop_index("ix_alert_policies_tenant_agent_type", table_name="alert_policies")
        op.drop_index("ix_alert_policies_tenant_type", table_name="alert_policies")
        op.drop_index("ix_alert_policies_tenant_agent", table_name="alert_policies")
        op.drop_table("alert_policies")
