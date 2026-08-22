"""create transactions table

Финансовая аналитика (см. app/finance/, specs/017-finance.md). Одна
строка на трату или доход; категория — фиксированный список в коде
(app/finance/models.py::CATEGORIES), не отдельная таблица.

Revision ID: 018_create_transactions
Revises: 017_task_goal_details
Create Date: 2026-08-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "018_create_transactions"
down_revision: Union[str, None] = "017_task_goal_details"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Личные траты и доходы (specs/017-finance.md)",
    )
    op.create_index(op.f("ix_transactions_id"), "transactions", ["id"], unique=False)
    op.create_index(
        op.f("ix_transactions_telegram_user_id"), "transactions", ["telegram_user_id"]
    )
    op.create_index(
        op.f("ix_transactions_occurred_at"), "transactions", ["occurred_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_transactions_occurred_at"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_telegram_user_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_id"), table_name="transactions")
    op.drop_table("transactions")
