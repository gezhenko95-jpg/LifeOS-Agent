"""
Модель задачи (Task) для LifeOS Agent
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
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

    description: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Что именно нужно сделать — детали, которые не влезли в название",
    )

    color: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Имя цвета метки для календаря (NULL — обычная задача)",
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

    recurrence: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Периодичность: daily | weekly | monthly | NULL (не повторяется)",
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Момент завершения задачи (NULL — ещё не завершена)",
    )

    in_progress: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment='Отметка "в работе" — независима от lifecycle-статуса (status)',
    )

    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Родительская задача (подзадача/эпик), NULL — верхний уровень",
    )

    contact_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Связанный контакт CRM (NULL — не связана)",
    )


class TaskComment(Base):
    """Комментарий к задаче — лог из нескольких записей, не одна
    перезаписываемая заметка (см. specs/022-tasks-v2.md)."""

    __tablename__ = "task_comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)

    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    text: Mapped[str] = mapped_column(String(1000), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
