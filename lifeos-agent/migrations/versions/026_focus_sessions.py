"""create focus_sessions table

Фокус-сессии/Pomodoro (specs/026-focus-sessions.md) — таймер+лог,
последнее из трёх пунктов бэклога 23-24.08. Опрос БД по work_ends_at/
break_ends_at, не in-memory job_queue.run_once (API и бот — разные
процессы, см. спеку).

Revision ID: 026_focus_sessions
Revises: 025_finance_debts
Create Date: 2026-08-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "026_focus_sessions"
down_revision: Union[str, None] = "025_finance_debts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "focus_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("work_minutes", sa.Integer(), nullable=False),
        sa.Column("break_minutes", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "work_ends_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Опрашивается джобой — момент, когда работа заканчивается",
        ),
        sa.Column("break_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            comment="in_progress / on_break / completed / cancelled",
        ),
        sa.Column("work_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("break_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        comment="Фокус-сессии/Pomodoro (specs/026-focus-sessions.md)",
    )
    op.create_index(op.f("ix_focus_sessions_id"), "focus_sessions", ["id"])
    op.create_index(
        op.f("ix_focus_sessions_telegram_user_id"),
        "focus_sessions",
        ["telegram_user_id"],
    )
    op.create_index(op.f("ix_focus_sessions_status"), "focus_sessions", ["status"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_focus_sessions_status"), table_name="focus_sessions")
    op.drop_index(
        op.f("ix_focus_sessions_telegram_user_id"), table_name="focus_sessions"
    )
    op.drop_index(op.f("ix_focus_sessions_id"), table_name="focus_sessions")
    op.drop_table("focus_sessions")
