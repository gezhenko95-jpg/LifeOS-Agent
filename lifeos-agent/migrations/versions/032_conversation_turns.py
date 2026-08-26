"""create conversation_turns table

Память диалога (specs/027-butler-personas-phase2.md, п.1) — последние
реплики ЭТОГО разговора для разговорного AI-фолбэка (chat_reply.py),
отдельно от долгосрочной MemoryEntry. Постоянная таблица, не
in-memory/TTL — решение владельца, деплои случаются по несколько раз
за сессию.

Revision ID: 032_conversation_turns
Revises: 031_task_goal_link
Create Date: 2026-08-26 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "032_conversation_turns"
down_revision: Union[str, None] = "031_task_goal_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "role",
            sa.String(length=10),
            nullable=False,
            comment="user|bot — кто произнёс реплику",
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Память диалога (specs/027-butler-personas-phase2.md)",
    )
    op.create_index(op.f("ix_conversation_turns_id"), "conversation_turns", ["id"])
    op.create_index(
        op.f("ix_conversation_turns_telegram_user_id"),
        "conversation_turns",
        ["telegram_user_id"],
    )
    op.create_index(
        op.f("ix_conversation_turns_created_at"),
        "conversation_turns",
        ["created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_conversation_turns_created_at"), table_name="conversation_turns"
    )
    op.drop_index(
        op.f("ix_conversation_turns_telegram_user_id"),
        table_name="conversation_turns",
    )
    op.drop_index(op.f("ix_conversation_turns_id"), table_name="conversation_turns")
    op.drop_table("conversation_turns")
