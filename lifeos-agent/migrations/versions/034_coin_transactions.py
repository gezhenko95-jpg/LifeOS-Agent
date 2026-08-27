"""create coin_transactions table

Магазин наград (specs/028-farm-tamagotchi-rewards.md, фаза 1) — вариант
(A) из спеки: заработок монет по-прежнему считается из истории чек-инов
(app/rewards/coins.py), а эта таблица добавляет сверху единственное, чего
не хватало, — расход. Append-only, из неё же выводится инвентарь
купленного (отдельной таблицы под него нет).

Revision ID: 034_coin_transactions
Revises: 033_assistant_nudge_dedup
Create Date: 2026-08-27 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "034_coin_transactions"
down_revision: Union[str, None] = "033_assistant_nudge_dedup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "coin_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "amount",
            sa.Integer(),
            nullable=False,
            comment="Монеты со знаком: трата отрицательная, начисление положительное",
        ),
        sa.Column(
            "reason",
            sa.String(length=32),
            nullable=False,
            comment="Повод движения, напр. purchase",
        ),
        sa.Column(
            "item_id",
            sa.String(length=64),
            nullable=True,
            comment="Товар из каталога (app/shop/catalog.py), если движение — покупка",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Расход монет магазина (specs/028-farm-tamagotchi-rewards.md)",
    )
    op.create_index(op.f("ix_coin_transactions_id"), "coin_transactions", ["id"])
    op.create_index(
        op.f("ix_coin_transactions_telegram_user_id"),
        "coin_transactions",
        ["telegram_user_id"],
    )
    op.create_index(
        op.f("ix_coin_transactions_item_id"), "coin_transactions", ["item_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_coin_transactions_item_id"), table_name="coin_transactions")
    op.drop_index(
        op.f("ix_coin_transactions_telegram_user_id"), table_name="coin_transactions"
    )
    op.drop_index(op.f("ix_coin_transactions_id"), table_name="coin_transactions")
    op.drop_table("coin_transactions")
