"""create checkins table

Ежедневный чек-ин мини-игры "🪙 Зайди и забери" в /ui (см.
app/rewards/). Одна строка на день, как HabitLog — уникальность
(telegram_user_id, checked_on) не даёт задвоить награду за один день.

Revision ID: 013_create_checkins
Revises: 012_add_perf_indexes
Create Date: 2026-08-16 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013_create_checkins"
down_revision: Union[str, None] = "012_add_perf_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "checkins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("checked_on", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id", "checked_on", name="uq_checkin_day"),
        comment='Отметка "заходил в этот день" для мини-игры с монетками',
    )
    op.create_index(op.f("ix_checkins_id"), "checkins", ["id"], unique=False)
    op.create_index(
        op.f("ix_checkins_telegram_user_id"), "checkins", ["telegram_user_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_checkins_telegram_user_id"), table_name="checkins")
    op.drop_index(op.f("ix_checkins_id"), table_name="checkins")
    op.drop_table("checkins")
