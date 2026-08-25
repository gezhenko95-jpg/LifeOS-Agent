"""tasks: link to a goal

Связь "задача ↔ цель" (живая проверка 25.08: "в цели тоже возможность
связывать цель с задачей") — прямая копия миграции 029_task_habit_link
для habit_id. ON DELETE SET NULL, не CASCADE — удаление цели не должно
утаскивать за собой задачи.

Revision ID: 031_task_goal_link
Revises: 030_debt_payments
Create Date: 2026-08-25 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "031_task_goal_link"
down_revision: Union[str, None] = "030_debt_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tasks",
        sa.Column(
            "goal_id",
            sa.Integer(),
            nullable=True,
            comment="Связанная цель (NULL — не связана)",
        ),
    )
    op.create_index(op.f("ix_tasks_goal_id"), "tasks", ["goal_id"])
    op.create_foreign_key(
        "fk_tasks_goal_id_goals",
        "tasks",
        "goals",
        ["goal_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_tasks_goal_id_goals", "tasks", type_="foreignkey")
    op.drop_index(op.f("ix_tasks_goal_id"), table_name="tasks")
    op.drop_column("tasks", "goal_id")
