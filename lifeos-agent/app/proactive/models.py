"""
Модель открытого проактивного вопроса (PendingPrompt).

См. specs/006-proactive-engagement.md. Одна строка на пользователя — новый
вопрос перезаписывает предыдущий неотвеченный (см. repository.upsert).
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PendingPrompt(Base):
    """Вопрос, заданный ботом проактивно, на который ещё не пришёл ответ."""

    __tablename__ = "pending_prompts"

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

    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Категория вопроса: goal | habit | project | preference | reflect",
    )

    question_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Текст вопроса, отправленный пользователю"
    )

    asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Когда вопрос был задан",
    )
