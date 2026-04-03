"""Add patterns table for cross-session pattern detection.

Revision ID: 005_add_patterns
Revises: 004_add_session_fix_note
Create Date: 2026-04-03

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_add_patterns"
down_revision: Union[str, None] = "004_add_session_fix_note"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Check if patterns table already exists
    if "patterns" not in inspector.get_table_names():
        op.create_table(
            "patterns",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("tenant_id", sa.String(64), nullable=False, index=True, server_default="local"),
            sa.Column("pattern_type", sa.String(32), nullable=False, index=True),
            sa.Column("agent_name", sa.String(255), nullable=False, index=True),
            sa.Column("severity", sa.String(16), nullable=False, server_default="warning"),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column(
                "detected_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
                index=True,
            ),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("affected_sessions", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("session_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("pattern_data", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("baseline_value", sa.Float(), nullable=True),
            sa.Column("current_value", sa.Float(), nullable=True),
            sa.Column("threshold", sa.Float(), nullable=True),
            sa.Column("change_percent", sa.Float(), nullable=True),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("resolved_by", sa.String(255), nullable=True),
        )

        # Create composite indexes for common query patterns
        op.create_index("ix_patterns_tenant_type", "patterns", ["tenant_id", "pattern_type"])
        op.create_index("ix_patterns_tenant_agent", "patterns", ["tenant_id", "agent_name"])
        op.create_index("ix_patterns_tenant_severity", "patterns", ["tenant_id", "severity"])
        op.create_index("ix_patterns_tenant_status", "patterns", ["tenant_id", "status"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Check if patterns table exists before dropping (idempotency)
    if "patterns" in inspector.get_table_names():
        op.drop_index("ix_patterns_tenant_status", table_name="patterns")
        op.drop_index("ix_patterns_tenant_severity", table_name="patterns")
        op.drop_index("ix_patterns_tenant_agent", table_name="patterns")
        op.drop_index("ix_patterns_tenant_type", table_name="patterns")
        op.drop_table("patterns")
