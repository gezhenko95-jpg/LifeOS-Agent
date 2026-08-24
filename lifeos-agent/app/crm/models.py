"""
Модель контакта личного CRM (specs/018-personal-crm.md) — «кому давно
не писал», «у кого скоро день рождения».
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Contact(Base):
    """Один контакт. `birthday_month`/`birthday_day` — оба NULL или оба
    заданы (год не хранится — фича про напоминания, не про возраст, см.
    спеку). `last_contact_at` получает `server_default=func.now()`, как
    `created_at` — свежедобавленный контакт не считается "давно не
    писал" с первого же дня."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Уникальный идентификатор контакта",
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Идентификатор пользователя в Telegram",
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="Имя")

    birthday_month: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Месяц дня рождения (1-12), без года"
    )

    birthday_day: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="День дня рождения (1-31), без года"
    )

    notes: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="Свободная заметка"
    )

    tags: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="Группы/теги через запятую"
    )

    nudge_after_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment='Свой порог "давно не писал" в днях (NULL — глобальный дефолт)',
    )

    last_contact_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="Момент последнего контакта — обновляется кнопкой «написал(а)»",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Когда контакт заведён",
    )
