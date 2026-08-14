"""
Модель записи Watchlist (фильм/книга/другое — «посмотреть/прочитать
позже») для LifeOS Agent. См. specs/010-media-inbox.md (Фаза 1).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WatchlistItem(Base):
    """Запись в списке "посмотреть/прочитать позже"."""

    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Уникальный идентификатор записи",
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Идентификатор пользователя в Telegram",
    )

    title: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Название фильма/книги"
    )

    media_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="other",
        comment="Тип: movie, book, other",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="to_watch",
        comment="Статус: to_watch, done",
    )

    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual",
        comment="Источник: manual, photo (Фаза 2 — Media Inbox)",
    )

    drive_file_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Ссылка на исходный файл на Google Drive (Фаза 2)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Дата и время добавления записи",
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Момент отметки «готово» (NULL — ещё не отмечена)",
    )
