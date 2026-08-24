"""
Модель фокус-сессии (Pomodoro), specs/026-focus-sessions.md.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

IN_PROGRESS = "in_progress"
ON_BREAK = "on_break"
COMPLETED = "completed"
CANCELLED = "cancelled"

# Активна = ещё идёт (работа или перерыв) — один такой сеанс на
# пользователя одновременно (см. FocusSessionService.start_session).
ACTIVE_STATUSES = frozenset({IN_PROGRESS, ON_BREAK})


class FocusSession(Base):
    """Одна сессия Pomodoro. work_ends_at/break_ends_at — конкретные
    моменты времени, не длительности: опрашивающая джоба
    (send_focus_notifications_job) сравнивает их с "сейчас", а не
    держит таймер в памяти (см. спеку, "Архитектура")."""

    __tablename__ = "focus_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )

    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        comment="Опциональная привязка к задаче",
    )

    work_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    break_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    work_ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    break_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    work_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    break_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
