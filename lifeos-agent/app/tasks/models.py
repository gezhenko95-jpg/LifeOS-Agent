"""
Модель задачи (Task) для LifeOS Agent
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Task(Base):
    """
    Модель задачи пользователя

    Простая модель для хранения задач, созданных через Telegram.
    Содержит минимальные поля для работы Sprint 1.
    """

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Уникальный идентификатор задачи",
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Идентификатор пользователя в Telegram",
    )

    title: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Название задачи, максимум 255 символов"
    )

    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Срок выполнения задачи (NULL - без срока)",
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
        comment="Статус задачи: active, completed, cancelled",
    )

    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="normal",
        comment="Приоритет задачи: low, normal, high",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Дата и время создания задачи",
    )

    reminded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Когда отправлено напоминание (NULL — ещё не отправлено)",
    )
