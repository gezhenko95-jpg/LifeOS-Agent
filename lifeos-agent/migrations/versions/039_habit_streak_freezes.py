"""add habit_streak_freezes table

Стрик-заморозка привычек (specs/029-engagement-features.md, по мотивам
Duolingo) — append-only ledger использования заморозок, тот же приём, что
coin_transactions/debt_payments. Без telegram_user_id: владение проверяется
через habits.id (тот же принцип, что у habit_logs).

Revision ID: 039_habit_streak_freezes
Revises: 038_pet_equipped_decor
Create Date: 2026-08-29 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "039_habit_streak_freezes"
down_revision: Union[str, None] = "038_pet_equipped_decor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "habit_streak_freezes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "habit_id",
            sa.Integer(),
            sa.ForeignKey("habits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("protected_on", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("habit_id", "protected_on", name="uq_habit_freeze_day"),
    )
    op.create_index(op.f("ix_habit_streak_freezes_id"), "habit_streak_freezes", ["id"])
    op.create_index(
        op.f("ix_habit_streak_freezes_habit_id"), "habit_streak_freezes", ["habit_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_habit_streak_freezes_habit_id"), table_name="habit_streak_freezes"
    )
    op.drop_index(op.f("ix_habit_streak_freezes_id"), table_name="habit_streak_freezes")
    op.drop_table("habit_streak_freezes")
