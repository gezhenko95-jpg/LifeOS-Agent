"""
Модели дайджестов Telegram-каналов (см. specs/013-channel-digests.md).

Дайджест — именованная тема пользователя ("ESG"), внутри которой лежат
чужие публичные Telegram-каналы. Бот читает их публичное веб-превью
(t.me/s/<channel>, см. app/digest/scraper.py) и присылает саммари новых
постов — по расписанию и/или по запросу.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Digest(Base):
    """Тема дайджеста пользователя ("ESG", "AI")."""

    __tablename__ = "digests"
    __table_args__ = (
        UniqueConstraint("telegram_user_id", "name", name="uq_digest_name"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Уникальный идентификатор дайджеста",
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Идентификатор пользователя в Telegram",
    )

    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Имя темы, один токен без пробелов (парсится из context.args)",
    )

    auto_frequency: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="daily, weekly или NULL — только по запросу (/digest <name>)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Дата и время создания дайджеста",
    )


class DigestChannel(Base):
    """Канал внутри дайджеста + водяной знак «что уже показано»."""

    __tablename__ = "digest_channels"
    __table_args__ = (
        UniqueConstraint("digest_id", "channel_username", name="uq_digest_channel"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Уникальный идентификатор записи о канале",
    )

    digest_id: Mapped[int] = mapped_column(
        ForeignKey("digests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Дайджест, в который добавлен канал",
    )

    channel_username: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Имя канала без @ и без t.me/ (нормализуется в сервисе)",
    )

    last_seen_post_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment=(
            "Максимальный уже показанный id поста. На ПАРЕ (дайджест, канал), "
            "не глобально на канал: один канал в двух дайджестах с разной "
            "частотой независимо отслеживает, что уже показано в каждом"
        ),
    )

    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Когда канал добавлен в дайджест",
    )
