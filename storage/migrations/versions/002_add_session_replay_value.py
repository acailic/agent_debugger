"""Add replay_value column to sessions.

Revision ID: 002_add_session_replay_value
Revises: 001_initial_schema
Create Date: 2026-03-23

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_add_session_replay_value"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("replay_value", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.create_index("ix_sessions_replay_value", "sessions", ["replay_value"])


def downgrade() -> None:
    op.drop_index("ix_sessions_replay_value", table_name="sessions")
    op.drop_column("sessions", "replay_value")
