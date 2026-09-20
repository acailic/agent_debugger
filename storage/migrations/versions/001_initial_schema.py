"""Initial schema with sessions, events, and checkpoints tables.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-03-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="local", index=True),
        sa.Column("agent_name", sa.String(255), nullable=False),
        sa.Column("framework", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
    )

    # Create events table
    op.create_table(
        "events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="local", index=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id"), nullable=False, index=True),
        sa.Column("parent_id", sa.String(36), nullable=True, index=True),
        sa.Column("event_type", sa.String(32), nullable=False, index=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("event_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
    )
    op.create_index("ix_events_tenant_session", "events", ["tenant_id", "session_id"])

    # Create checkpoints table
    op.create_table(
        "checkpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="local", index=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id"), nullable=False, index=True),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("memory", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
    )


def downgrade() -> None:
    op.drop_table("checkpoints")
    op.drop_index("ix_events_tenant_session", table_name="events")
    op.drop_table("events")
    op.drop_table("sessions")
