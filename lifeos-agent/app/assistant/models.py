"""
Настройка активного персонажа (specs/020-butler-personas.md) — одна
строка на пользователя, переключается только на /ui (не в боте).
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.assistant.personas import DEFAULT_PERSONA
from app.db.base import Base


class AssistantSettings(Base):
    __tablename__ = "assistant_settings"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Уникальный идентификатор записи",
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        index=True,
        comment="Идентификатор пользователя в Telegram",
    )

    persona: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=DEFAULT_PERSONA.value,
        comment="Активный персонаж: butler|trainer|director|financier",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Момент последнего переключения",
    )

    # Дедуп незапланированных сообщений персонажа (specs/027-butler-
    # personas-phase2.md, п.2) — без этой пары один и тот же повод
    # (например, оборванный стрик) слался бы на ОБОИХ дневных слотах,
    # где проверяется триггер (день_since не меняется в течение дня).
    last_nudge_sent_on: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Дата последнего незапланированного сообщения персонажа",
    )

    last_nudge_trigger: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Ключ триггера последнего незапланированного сообщения, "
        "напр. habit_streak:12",
    )
