"""create watchlist_items table

Watchlist — Фаза 1 Media Inbox (см. specs/010-media-inbox.md):
"посмотреть/прочитать позже" (фильмы/книги), управляется из Telegram.
drive_file_url/source="photo" зарезервированы под Фазу 2 (пока не
используются).

Revision ID: 010_create_watchlist_items
Revises: 009_add_recurrence_completed_at
Create Date: 2026-08-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010_create_watchlist_items"
down_revision: Union[str, None] = "009_add_recurrence_completed_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("drive_file_url", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        comment='Запись "посмотреть/прочитать позже" (фильм/книга/другое)',
    )
    op.create_index(
        op.f("ix_watchlist_items_id"), "watchlist_items", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_watchlist_items_telegram_user_id"),
        "watchlist_items",
        ["telegram_user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_watchlist_items_telegram_user_id"), table_name="watchlist_items"
    )
    op.drop_index(op.f("ix_watchlist_items_id"), table_name="watchlist_items")
    op.drop_table("watchlist_items")
