"""create mood_entries table

Трекер настроения Daylio-style (см. app/mood/, specs/019-mood-tracker.md).
Одна строка на отметку — тап по эмодзи-оценке 1-5, несколько записей в
день не ошибка.

Revision ID: 020_create_mood_entries
Revises: 019_create_contacts
Create Date: 2026-08-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020_create_mood_entries"
down_revision: Union[str, None] = "019_create_contacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "mood_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column(
            "logged_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Отметки настроения (specs/019-mood-tracker.md)",
    )
    op.create_index(op.f("ix_mood_entries_id"), "mood_entries", ["id"], unique=False)
    op.create_index(
        op.f("ix_mood_entries_telegram_user_id"), "mood_entries", ["telegram_user_id"]
    )
    op.create_index(op.f("ix_mood_entries_logged_at"), "mood_entries", ["logged_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_mood_entries_logged_at"), table_name="mood_entries")
    op.drop_index(op.f("ix_mood_entries_telegram_user_id"), table_name="mood_entries")
    op.drop_index(op.f("ix_mood_entries_id"), table_name="mood_entries")
    op.drop_table("mood_entries")
