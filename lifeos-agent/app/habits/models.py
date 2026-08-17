"""
Модели привычек (Habit) и их логов выполнения (HabitLog).
"""

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Habit(Base):
    """Привычка пользователя."""

    __tablename__ = "habits"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Уникальный идентификатор привычки",
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Идентификатор пользователя в Telegram",
    )

    title: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Название привычки"
    )

    description: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Короткое описание: зачем эта привычка, что считается выполнением",
    )

    reminder_time: Mapped[Optional[time]] = mapped_column(
        Time,
        nullable=True,
        comment="Местное время ежедневного напоминания (NULL — не напоминать)",
    )

    last_reminded_on: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="За какой день уже напомнили — чтобы не слать повторно",
    )

    archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Архивная привычка не участвует в списках/брифинге",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Дата и время создания привычки",
    )


class HabitLog(Base):
    """Отметка о выполнении привычки за конкретный день."""

    __tablename__ = "habit_logs"
    __table_args__ = (
        UniqueConstraint("habit_id", "completed_on", name="uq_habit_log_day"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Уникальный идентификатор лога",
    )

    habit_id: Mapped[int] = mapped_column(
        ForeignKey("habits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Привычка, к которой относится отметка",
    )

    completed_on: Mapped[date] = mapped_column(
        Date, nullable=False, comment="За какой день сделана отметка"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Когда фактически была сделана отметка",
    )
