"""add equipped_decor_item_id to pets

Визуальный питомец (specs/028-farm-tamagotchi-rewards.md, последний
осознанно отложенный пункт) — надевание купленных в магазине украшений.
В отличие от остальных полей Pet, это НЕ производное значение: сам факт
владения товаром выводится из истории покупок (app/shop/), а какой из
владеемых предметов надет ПРЯМО СЕЙЧАС — собственный выбор пользователя,
который негде больше хранить.

Revision ID: 038_pet_equipped_decor
Revises: 037_farm_pet_notifications
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "038_pet_equipped_decor"
down_revision: Union[str, None] = "037_farm_pet_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "pets",
        sa.Column(
            "equipped_decor_item_id",
            sa.String(length=64),
            nullable=True,
            comment="Товар из app/shop/catalog.py (kind=decor), надетый сейчас",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("pets", "equipped_decor_item_id")
