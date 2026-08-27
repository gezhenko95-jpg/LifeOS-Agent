"""create pets table

Питомец (specs/028-farm-tamagotchi-rewards.md, фаза 3). Один на аккаунт
(ответ владельца 27.08) — telegram_user_id уникален. Голод/настроение/
состояние не хранятся: они выводятся из last_fed_at чистой функцией
(app/pet/service.py) — хранится только момент последнего кормления и
честный счётчик смертей, который кормление/оживление не обнуляет.

Revision ID: 036_pets
Revises: 035_farm
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "036_pets"
down_revision: Union[str, None] = "035_farm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_fed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Голод/настроение/болезнь/смерть — чистая функция от этого поля",
        ),
        sa.Column(
            "deaths_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Сколько раз питомец умирал от пренебрежения",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id", name="uq_pets_telegram_user_id"),
        comment="Один питомец на аккаунт (specs/028-farm-tamagotchi-rewards.md)",
    )
    op.create_index(op.f("ix_pets_id"), "pets", ["id"])
    op.create_index(op.f("ix_pets_telegram_user_id"), "pets", ["telegram_user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_pets_telegram_user_id"), table_name="pets")
    op.drop_index(op.f("ix_pets_id"), table_name="pets")
    op.drop_table("pets")
