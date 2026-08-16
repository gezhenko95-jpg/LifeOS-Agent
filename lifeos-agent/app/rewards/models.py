"""
Модель ежедневной отметки визита (Checkin) — мини-игра "зайди и забери
монетки" в /ui. См. app/rewards/coins.py для самого расчёта наград.
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Checkin(Base):
    """Одна отметка "заходил в этот день" — как HabitLog, но не про
    привычку, а про сам факт визита на сайт."""

    __tablename__ = "checkins"
    __table_args__ = (
        UniqueConstraint("telegram_user_id", "checked_on", name="uq_checkin_day"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Уникальный идентификатор отметки",
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Идентификатор пользователя в Telegram",
    )

    checked_on: Mapped[date] = mapped_column(
        Date, nullable=False, comment="За какой день сделана отметка"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Когда фактически была сделана отметка",
    )
