"""create farm tables

Ферма (specs/028-farm-tamagotchi-rewards.md, фаза 2): грядки, расход
купленных в магазине семян/ускорителей, учёт собранного сена. Тот же
ledger-приём, что у coin_transactions (034) — остатки выводятся из
истории, отдельных изменяемых счётчиков нет.

Revision ID: 035_farm
Revises: 034_coin_transactions
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "035_farm"
down_revision: Union[str, None] = "034_coin_transactions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "farm_plots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "planted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "ready_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Момент, когда грядку можно убирать",
        ),
        sa.Column(
            "fertilized",
            sa.Boolean(),
            nullable=False,
            server_default="0",
            comment="Удобрение применено при посадке",
        ),
        sa.Column(
            "hay_yield",
            sa.Integer(),
            nullable=False,
            comment="Сколько сена даст сбор этой грядки",
        ),
        sa.Column(
            "harvested_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="NULL — ещё растёт или созрела, но не собрана",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Грядки фермы (specs/028-farm-tamagotchi-rewards.md)",
    )
    op.create_index(op.f("ix_farm_plots_id"), "farm_plots", ["id"])
    op.create_index(
        op.f("ix_farm_plots_telegram_user_id"), "farm_plots", ["telegram_user_id"]
    )

    op.create_table(
        "farm_supply_use",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "item_id",
            sa.String(length=64),
            nullable=False,
            comment="Товар из app/shop/catalog.py — seed_clover/booster_*",
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Расход купленных семян/ускорителей на нужды фермы",
    )
    op.create_index(op.f("ix_farm_supply_use_id"), "farm_supply_use", ["id"])
    op.create_index(
        op.f("ix_farm_supply_use_telegram_user_id"),
        "farm_supply_use",
        ["telegram_user_id"],
    )
    op.create_index(op.f("ix_farm_supply_use_item_id"), "farm_supply_use", ["item_id"])

    op.create_table(
        "hay_consumption",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Сено, скормленное питомцу (app/pet/, фаза 3)",
    )
    op.create_index(op.f("ix_hay_consumption_id"), "hay_consumption", ["id"])
    op.create_index(
        op.f("ix_hay_consumption_telegram_user_id"),
        "hay_consumption",
        ["telegram_user_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_hay_consumption_telegram_user_id"), table_name="hay_consumption"
    )
    op.drop_index(op.f("ix_hay_consumption_id"), table_name="hay_consumption")
    op.drop_table("hay_consumption")

    op.drop_index(op.f("ix_farm_supply_use_item_id"), table_name="farm_supply_use")
    op.drop_index(
        op.f("ix_farm_supply_use_telegram_user_id"), table_name="farm_supply_use"
    )
    op.drop_index(op.f("ix_farm_supply_use_id"), table_name="farm_supply_use")
    op.drop_table("farm_supply_use")

    op.drop_index(op.f("ix_farm_plots_telegram_user_id"), table_name="farm_plots")
    op.drop_index(op.f("ix_farm_plots_id"), table_name="farm_plots")
    op.drop_table("farm_plots")
