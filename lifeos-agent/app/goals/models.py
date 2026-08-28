"""
Модель цели (Goal) для LifeOS Agent.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Goal(Base):
    """Долгосрочная цель пользователя со структурированным прогрессом."""

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Уникальный идентификатор цели",
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Идентификатор пользователя в Telegram",
    )

    title: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Название цели"
    )

    target_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, comment="Целевая дата (NULL — без срока)"
    )

    description: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="Зачем эта цель и что считается успехом"
    )

    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Процент выполнения, 0..100",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="Статус цели: active, completed, abandoned",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Дата и время создания цели",
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата и время последнего обновления",
    )

    boss_reward_claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Квест-босс (specs/030, по мотивам Habitica) — момент, "
        "когда за ДОСТИЖЕНИЕ 100% один раз начислена награда. НЕ "
        "сбрасывается, если прогресс потом утащили обратно ниже 100 "
        "(GoalService.update_goal снимает status=COMPLETED симметрично) "
        "— иначе перетаскивание ползунка 100→90→100 фармило бы монеты "
        "бесконечно; 'босс побеждён' — разовый факт, как deaths_count "
        "у питомца.",
    )
