"""add boss_reward_claimed_at to goals

Квест-босс (specs/030-more-engagement-features.md, по мотивам Habitica)
— одноразовая награда за достижение 100% прогресса. Дедуп-поле, не
сбрасывается, если прогресс потом упал ниже 100 (тот же принцип, что
Pet.deaths_count).

Revision ID: 041_goal_boss_reward
Revises: 040_pet_last_adventure
Create Date: 2026-08-29 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "041_goal_boss_reward"
down_revision: Union[str, None] = "040_pet_last_adventure"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "goals",
        sa.Column(
            "boss_reward_claimed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Одноразовая награда за 100% прогресса — не сбрасывается",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("goals", "boss_reward_claimed_at")
