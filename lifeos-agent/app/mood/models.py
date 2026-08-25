"""
Модель записи настроения (specs/019-mood-tracker.md) — Daylio-style:
один тап по оценке 1-7, без обязательного текста.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Живая проверка 25.08: было 1-5 ("так себе"/"норм" почти не отличались
# по ощущению) — расширено до 1-7. На /ui эмодзи заменены на свой набор
# SVG-глифов (см. index.html), в боте эмодзи остаются — Telegram не
# рисует кастомные SVG в инлайн-кнопках.
MIN_SCORE = 1
MAX_SCORE = 7

# Эмодзи по оценке — используется в боте (keyboards.py/callbacks.py).
# /ui больше не использует этот словарь для пикера (свой набор SVG-глифов
# по той же оценке 1-7, см. index.html), но старые записи в дневнике
# настроения на /ui всё ещё показывают эмодзи рядом с числом.
SCORE_EMOJI: dict[int, str] = {
    1: "😭",
    2: "😢",
    3: "😕",
    4: "😐",
    5: "🙂",
    6: "😄",
    7: "🤩",
}


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
        Integer, nullable=False, comment="Оценка настроения, 1-7"
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
