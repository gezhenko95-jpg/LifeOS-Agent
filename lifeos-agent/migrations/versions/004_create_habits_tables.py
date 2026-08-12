"""create habits tables

Revision ID: 004_create_habits_tables
Revises: 003_add_priority_to_tasks
Create Date: 2026-08-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_create_habits_tables"
down_revision: Union[str, None] = "003_add_priority_to_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "habits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Привычка пользователя",
    )
    op.create_index(op.f("ix_habits_id"), "habits", ["id"], unique=False)
    op.create_index(
        op.f("ix_habits_telegram_user_id"), "habits", ["telegram_user_id"], unique=False
    )

    op.create_table(
        "habit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("habit_id", sa.Integer(), nullable=False),
        sa.Column("completed_on", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["habit_id"], ["habits.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("habit_id", "completed_on", name="uq_habit_log_day"),
        comment="Отметка о выполнении привычки за день",
    )
    op.create_index(op.f("ix_habit_logs_id"), "habit_logs", ["id"], unique=False)
    op.create_index(
        op.f("ix_habit_logs_habit_id"), "habit_logs", ["habit_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_habit_logs_habit_id"), table_name="habit_logs")
    op.drop_index(op.f("ix_habit_logs_id"), table_name="habit_logs")
    op.drop_table("habit_logs")
    op.drop_index(op.f("ix_habits_telegram_user_id"), table_name="habits")
    op.drop_index(op.f("ix_habits_id"), table_name="habits")
    op.drop_table("habits")
