"""add description and reminders to habits

Привычка обзаводится тремя полями: короткое описание («зачем она»),
время ежедневного напоминания и отметка «за какой день уже напоминали»
(без неё джоба, которая крутится раз в минуту, слала бы напоминание
каждую минуту после наступления времени).

Revision ID: 015_habit_details
Revises: 014_create_digests
Create Date: 2026-08-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015_habit_details"
down_revision: Union[str, None] = "014_create_digests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "habits",
        sa.Column("description", sa.String(length=255), nullable=True),
    )
    op.add_column("habits", sa.Column("reminder_time", sa.Time(), nullable=True))
    op.add_column("habits", sa.Column("last_reminded_on", sa.Date(), nullable=True))

    # Джоба напоминаний ходит за «у кого сейчас пора напомнить» раз в
    # минуту: без индекса это seq scan по всем привычкам всех
    # пользователей каждую минуту (тот же приём, что у частичных
    # индексов под напоминания задач в миграции 012).
    op.create_index(
        "ix_habits_reminder_time",
        "habits",
        ["reminder_time"],
        unique=False,
        postgresql_where=sa.text("reminder_time IS NOT NULL AND archived = false"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_habits_reminder_time", table_name="habits")
    op.drop_column("habits", "last_reminded_on")
    op.drop_column("habits", "reminder_time")
    op.drop_column("habits", "description")
