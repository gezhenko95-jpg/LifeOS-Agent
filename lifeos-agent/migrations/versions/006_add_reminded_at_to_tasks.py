"""add reminded_at to tasks

Revision ID: 006_add_reminded_at_to_tasks
Revises: 005_create_goals_table
Create Date: 2026-08-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_add_reminded_at_to_tasks"
down_revision: Union[str, None] = "005_create_goals_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tasks",
        sa.Column(
            "reminded_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Когда отправлено напоминание (NULL — ещё не отправлено)",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("tasks", "reminded_at")
