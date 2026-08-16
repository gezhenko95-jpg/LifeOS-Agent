"""create digest tables

Дайджесты чужих публичных Telegram-каналов (см. app/digest/,
specs/013-channel-digests.md). digest_channels ссылаются на digests с
ON DELETE CASCADE сразу (в отличие от habit_logs, которым каскад
пришлось добавлять миграцией 007 постфактум).

Revision ID: 014_create_digests
Revises: 013_create_checkins
Create Date: 2026-08-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014_create_digests"
down_revision: Union[str, None] = "013_create_checkins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "digests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("auto_frequency", sa.String(length=10), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id", "name", name="uq_digest_name"),
        comment="Тема дайджеста Telegram-каналов",
    )
    op.create_index(op.f("ix_digests_id"), "digests", ["id"], unique=False)
    op.create_index(
        op.f("ix_digests_telegram_user_id"), "digests", ["telegram_user_id"]
    )

    op.create_table(
        "digest_channels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("digest_id", sa.Integer(), nullable=False),
        sa.Column("channel_username", sa.String(length=64), nullable=False),
        sa.Column("last_seen_post_id", sa.Integer(), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["digest_id"], ["digests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("digest_id", "channel_username", name="uq_digest_channel"),
        comment="Публичный Telegram-канал внутри дайджеста",
    )
    op.create_index(
        op.f("ix_digest_channels_id"), "digest_channels", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_digest_channels_digest_id"), "digest_channels", ["digest_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_digest_channels_digest_id"), table_name="digest_channels")
    op.drop_index(op.f("ix_digest_channels_id"), table_name="digest_channels")
    op.drop_table("digest_channels")
    op.drop_index(op.f("ix_digests_telegram_user_id"), table_name="digests")
    op.drop_index(op.f("ix_digests_id"), table_name="digests")
    op.drop_table("digests")
