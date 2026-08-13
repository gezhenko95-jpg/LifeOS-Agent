"""create pending_prompts table

Хранит один открытый проактивный вопрос на пользователя (см.
specs/006-proactive-engagement.md). Одна строка на telegram_user_id —
новый вопрос перезаписывает предыдущий неотвеченный (upsert), очередь не
копится.

Revision ID: 008_create_pending_prompts_table
Revises: 007_cascade_delete_habit_logs
Create Date: 2026-08-13 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_create_pending_prompts_table"
down_revision: Union[str, None] = "007_cascade_delete_habit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pending_prompts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column(
            "asked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Открытый проактивный вопрос, ждущий ответа пользователя",
    )
    op.create_index(
        op.f("ix_pending_prompts_id"), "pending_prompts", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_pending_prompts_telegram_user_id"),
        "pending_prompts",
        ["telegram_user_id"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_pending_prompts_telegram_user_id"), table_name="pending_prompts"
    )
    op.drop_index(op.f("ix_pending_prompts_id"), table_name="pending_prompts")
    op.drop_table("pending_prompts")
