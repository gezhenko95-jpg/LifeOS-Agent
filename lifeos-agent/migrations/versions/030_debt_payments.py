"""debts: план рассрочки + лог фактических платежей

Отчёт владельца 24.08, вечер #6, волна 7: "график платежей и прочее" —
и то (лог + история), и другое (план: ежемесячный платёж, следующий
срок). Новая таблица debt_payments (append-only, копия task_comments) +
две nullable-колонки на debts.

Revision ID: 030_debt_payments
Revises: 029_task_habit_link
Create Date: 2026-08-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "030_debt_payments"
down_revision: Union[str, None] = "029_task_habit_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "debts",
        sa.Column(
            "monthly_payment",
            sa.Integer(),
            nullable=True,
            comment="План рассрочки — ежемесячный платёж в рублях (NULL — нет плана)",
        ),
    )
    op.add_column(
        "debts",
        sa.Column(
            "next_payment_due",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Дата следующего платежа по плану",
        ),
    )
    op.create_table(
        "debt_payments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "debt_id",
            sa.Integer(),
            sa.ForeignKey("debts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(op.f("ix_debt_payments_id"), "debt_payments", ["id"])
    op.create_index(op.f("ix_debt_payments_debt_id"), "debt_payments", ["debt_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_debt_payments_debt_id"), table_name="debt_payments")
    op.drop_index(op.f("ix_debt_payments_id"), table_name="debt_payments")
    op.drop_table("debt_payments")
    op.drop_column("debts", "next_payment_due")
    op.drop_column("debts", "monthly_payment")
