"""
Модель записи настроения (specs/019-mood-tracker.md) — Daylio-style:
один тап по эмодзи-оценке 1-5, без обязательного текста.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MIN_SCORE = 1
MAX_SCORE = 5

# Эмодзи по оценке — используется и в боте (keyboards.py/callbacks.py),
# и на /ui через тот же смысл (там своя копия в JS, как категории
# финансов — см. app/finance/models.py::CATEGORIES).
SCORE_EMOJI: dict[int, str] = {1: "😢", 2: "😕", 3: "😐", 4: "🙂", 5: "😄"}


class MoodEntry(Base):
    """Одна отметка настроения. Несколько записей в один день —
    не ошибка (см. спеку): повторный тап уточняет, а не портит историю."""

    __tablename__ = "mood_entries"

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

    score: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Оценка настроения, 1-5"
    )

    note: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Необязательная заметка — не заполняется кнопкой в этой итерации",
    )

    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="Момент отметки",
    )
