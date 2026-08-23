"""create assistant_settings table

Настройка активного персонажа бота (см. app/assistant/,
specs/020-butler-personas.md). Одна строка на пользователя, дефолт
"butler" — переключается только на /ui.

Revision ID: 021_create_assistant_settings
Revises: 020_create_mood_entries
Create Date: 2026-08-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021_create_assistant_settings"
down_revision: Union[str, None] = "020_create_mood_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "assistant_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "persona",
            sa.String(length=20),
            server_default="butler",
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Активный персонаж бота (specs/020-butler-personas.md)",
    )
    op.create_index(
        op.f("ix_assistant_settings_id"), "assistant_settings", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_assistant_settings_telegram_user_id"),
        "assistant_settings",
        ["telegram_user_id"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_assistant_settings_telegram_user_id"),
        table_name="assistant_settings",
    )
    op.drop_index(op.f("ix_assistant_settings_id"), table_name="assistant_settings")
    op.drop_table("assistant_settings")
