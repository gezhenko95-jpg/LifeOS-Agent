"""create memory_entries table

Revision ID: 002_create_memory_entries_table
Revises: 001_create_tasks_table
Create Date: 2026-08-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_create_memory_entries_table"
down_revision: Union[str, None] = "001_create_tasks_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "memory_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        comment="Запись долговременной памяти пользователя",
    )
    op.create_index(
        op.f("ix_memory_entries_id"), "memory_entries", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_memory_entries_telegram_user_id"),
        "memory_entries",
        ["telegram_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_entries_type"), "memory_entries", ["type"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_memory_entries_type"), table_name="memory_entries")
    op.drop_index(
        op.f("ix_memory_entries_telegram_user_id"), table_name="memory_entries"
    )
    op.drop_index(op.f("ix_memory_entries_id"), table_name="memory_entries")
    op.drop_table("memory_entries")
