"""tasks: in_progress_started_at

Таймер "в работе" на /ui (отчёт владельца 24.08, вечер #6) — раньше
in_progress был голым boolean без временной метки, посчитать elapsed
было не от чего. NULL — сейчас не в работе.

Revision ID: 027_task_in_progress_started_at
Revises: 026_focus_sessions
Create Date: 2026-08-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "027_task_in_progress_started_at"
down_revision: Union[str, None] = "026_focus_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tasks",
        sa.Column(
            "in_progress_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Момент последнего включения "в работе" — NULL, если '
            "сейчас не в работе.",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("tasks", "in_progress_started_at")
