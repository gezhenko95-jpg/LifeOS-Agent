"""create debts table

Долги/задолженности со сроками (specs/017-finance.md, довесок из
бэклога 23-24.08 — "добавить задолжности и сроки"). Отдельная
сущность, не транзакция: долг живёт месяцами и имеет остаток, а
транзакция — разовая запись траты/дохода. Ежемесячный платёж по
кредиту по-прежнему логируется обычной тратой в категории "credit"
(не меняется этой миграцией) — Debt только отслеживает сам факт долга
и срок, в расчёт свободных денег не встраивается.

Revision ID: 025_finance_debts
Revises: 024_crm_tags_nudge
Create Date: 2026-08-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "025_finance_debts"
down_revision: Union[str, None] = "024_crm_tags_nudge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "debts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "total_amount",
            sa.Integer(),
            nullable=False,
            comment="Исходная сумма долга в рублях",
        ),
        sa.Column(
            "remaining_amount",
            sa.Integer(),
            nullable=False,
            comment="Текущий остаток — уменьшается платежами",
        ),
        sa.Column(
            "due_date",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Срок закрытия (NULL — без срока)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Долги/задолженности (specs/017-finance.md, довесок)",
    )
    op.create_index(op.f("ix_debts_id"), "debts", ["id"])
    op.create_index(op.f("ix_debts_telegram_user_id"), "debts", ["telegram_user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_debts_telegram_user_id"), table_name="debts")
    op.drop_index(op.f("ix_debts_id"), table_name="debts")
    op.drop_table("debts")
