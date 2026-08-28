"""add last_adventure_on to pets

Приключения питомца (specs/030-more-engagement-features.md, по мотивам
Finch) — дедуп раз в день, тот же приём, что hungry_notified_at, только
по дате: приключение либо было сегодня, либо нет.

Revision ID: 040_pet_last_adventure
Revises: 039_habit_streak_freezes
Create Date: 2026-08-29 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "040_pet_last_adventure"
down_revision: Union[str, None] = "039_habit_streak_freezes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "pets",
        sa.Column(
            "last_adventure_on",
            sa.Date(),
            nullable=True,
            comment="Дедуп 'приключения' — раз в день, если питомец сегодня покормлен",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("pets", "last_adventure_on")
