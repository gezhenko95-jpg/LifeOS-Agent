"""add description to tasks and goals, color to tasks

Описание было только у привычек (миграция 015) — теперь оно есть у всех
основных сущностей: задача и цель тоже нередко требуют строки «что
именно считается сделанным». Цвет — только у задач: это способ разметить
календарь по смыслу (работа/дом/здоровье), а привычки и цели в
календаре не показываются.

Revision ID: 017_task_goal_details
Revises: 016_watchlist_media
Create Date: 2026-08-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017_task_goal_details"
down_revision: Union[str, None] = "016_watchlist_media"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tasks", sa.Column("description", sa.String(length=500), nullable=True)
    )
    # Имя цвета, а не HEX: палитра фиксированная и красится переменными
    # темы, поэтому «red» переживает смену оформления, а «#dc2626» — нет.
    op.add_column("tasks", sa.Column("color", sa.String(length=20), nullable=True))
    op.add_column(
        "goals", sa.Column("description", sa.String(length=500), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("goals", "description")
    op.drop_column("tasks", "color")
    op.drop_column("tasks", "description")
