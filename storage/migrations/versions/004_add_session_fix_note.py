"""Add fix_note column to sessions.

Revision ID: 004_add_session_fix_note
Revises: 003_add_research_features
Create Date: 2026-03-26

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_add_session_fix_note"
down_revision: Union[str, None] = "003_add_research_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    session_columns = {col["name"] for col in inspector.get_columns("sessions")}

    if "fix_note" not in session_columns:
        op.add_column("sessions", sa.Column("fix_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "fix_note")
