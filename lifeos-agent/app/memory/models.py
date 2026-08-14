"""
Модель записи долговременной памяти (MemoryEntry) для LifeOS Agent.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import BigInteger, String

from app.db.base import Base


class MemoryType(str, Enum):
    """Типы записей памяти, см. specs/001-memory.md."""

    FACT = "fact"
    PREFERENCE = "preference"
    GOAL = "goal"
    PROJECT = "project"
    JOURNAL = "journal"


class MemoryEntry(Base):
    """
    Запись долговременной памяти пользователя.

    Один тип таблицы для facts/preferences/goals/projects/journal —
    см. specs/001-memory.md. Conversations (история диалога) сюда не
    входят — это отдельный поток данных, не реализован в этой версии.
    """

    __tablename__ = "memory_entries"

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

    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Тип записи: fact, preference, goal, project, journal",
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Текст записи",
    )

    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="manual",
        comment="Источник записи: telegram, manual, ai",
    )

    archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Архивная запись не участвует в поиске/контексте по умолчанию",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Дата и время создания записи",
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата и время последнего обновления записи",
    )

    embedding: Mapped[Optional[list[float]]] = mapped_column(
        # none_as_null=True — иначе Python None сохраняется как JSON-
        # литерал "null", а не SQL NULL, и все IS NULL/IS NOT NULL
        # запросы (list_with_embeddings/list_missing_embeddings) молча
        # ломаются.
        JSON(none_as_null=True),
        nullable=True,
        comment=(
            "Вектор embedding для семантического поиска (см. "
            "specs/011-semantic-memory-search.md), NULL — ещё не "
            "посчитан (доливается фоновой job)"
        ),
    )
