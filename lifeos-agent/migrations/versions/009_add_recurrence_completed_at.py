"""add recurrence and completed_at to tasks

recurrence — для повторяющихся задач (specs/002-tasks.md, раздел
Recurring Tasks): daily | weekly | monthly | NULL.
completed_at — момент завершения задачи; нужен и повторяющимся задачам
(чтобы считать следующую дату от даты due, а не completed), и
еженедельному дайджесту ("сколько задач выполнено за неделю" — раньше
такого не сосчитать было, у задачи не было отметки времени завершения).

Revision ID: 009_add_recurrence_completed_at
Revises: 008_create_pending_prompts_table
Create Date: 2026-08-13 00:00:00.000000

Примечание: id ревизии укорочен относительно "полного" имени файла —
alembic_version.version_num имеет тип varchar(32), а "009_add_recurrence_
and_completed_at_to_tasks" (44 символа) в него не помещается.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_add_recurrence_completed_at"
down_revision: Union[str, None] = "008_create_pending_prompts_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tasks",
        sa.Column(
            "recurrence",
            sa.String(length=20),
            nullable=True,
            comment="Периодичность: daily | weekly | monthly | NULL (не повторяется)",
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Момент завершения задачи (NULL — ещё не завершена)",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("tasks", "completed_at")
    op.drop_column("tasks", "recurrence")
