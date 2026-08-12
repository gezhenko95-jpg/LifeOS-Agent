"""add priority to tasks

Revision ID: 003_add_priority_to_tasks
Revises: 002_create_memory_entries_table
Create Date: 2026-08-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_priority_to_tasks"
down_revision: Union[str, None] = "002_create_memory_entries_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tasks",
        sa.Column(
            "priority",
            sa.String(length=20),
            nullable=False,
            server_default="normal",
            comment="Приоритет задачи: low, normal, high",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("tasks", "priority")
