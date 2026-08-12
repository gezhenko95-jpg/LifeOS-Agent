"""cascade delete habit_logs when habit is deleted

Баг: удаление привычки с логами падало с ForeignKeyViolationError —
habit_logs ссылались на habits.id без ON DELETE CASCADE, а приложение
не удаляло логи перед удалением привычки.

Revision ID: 007_cascade_delete_habit_logs
Revises: 006_add_reminded_at_to_tasks
Create Date: 2026-08-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_cascade_delete_habit_logs"
down_revision: Union[str, None] = "006_add_reminded_at_to_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("habit_logs_habit_id_fkey", "habit_logs", type_="foreignkey")
    op.create_foreign_key(
        "habit_logs_habit_id_fkey",
        "habit_logs",
        "habits",
        ["habit_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("habit_logs_habit_id_fkey", "habit_logs", type_="foreignkey")
    op.create_foreign_key(
        "habit_logs_habit_id_fkey", "habit_logs", "habits", ["habit_id"], ["id"]
    )
