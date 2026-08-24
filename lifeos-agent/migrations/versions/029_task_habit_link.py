"""tasks: link to a habit

Связь "задача ↔ привычка" (отчёт владельца 24.08, вечер #6: "чтобы в
задачу можно было привязать привычку") — прямая копия миграции
023_task_contact_link для contact_id. ON DELETE SET NULL, не CASCADE —
удаление привычки не должно утаскивать за собой задачи.

Revision ID: 029_task_habit_link
Revises: 028_contact_comments
Create Date: 2026-08-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "029_task_habit_link"
down_revision: Union[str, None] = "028_contact_comments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tasks",
        sa.Column(
            "habit_id",
            sa.Integer(),
            nullable=True,
            comment="Связанная привычка (NULL — не связана)",
        ),
    )
    op.create_index(op.f("ix_tasks_habit_id"), "tasks", ["habit_id"])
    op.create_foreign_key(
        "fk_tasks_habit_id_habits",
        "tasks",
        "habits",
        ["habit_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_tasks_habit_id_habits", "tasks", type_="foreignkey")
    op.drop_index(op.f("ix_tasks_habit_id"), table_name="tasks")
    op.drop_column("tasks", "habit_id")
