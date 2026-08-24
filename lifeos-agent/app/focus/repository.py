"""
Репозиторий фокус-сессий. Единственное место с SQL к `focus_sessions`.
"""

from datetime import datetime

from sqlalchemy import func, select

from app.core.repository import BaseRepository
from app.focus.models import (
    ACTIVE_STATUSES,
    COMPLETED,
    IN_PROGRESS,
    ON_BREAK,
    FocusSession,
)


class FocusSessionRepository(BaseRepository[FocusSession]):
    model = FocusSession

    async def get_active(self, telegram_user_id: int) -> FocusSession | None:
        query = select(FocusSession).where(
            FocusSession.telegram_user_id == telegram_user_id,
            FocusSession.status.in_(ACTIVE_STATUSES),
        )
        result = await self._session.execute(query)
        return result.scalars().first()

    async def list_due_work_end(self, now: datetime) -> list[FocusSession]:
        """Сессии, у которых работа уже должна была закончиться, но
        уведомление ещё не отправлено — без фильтра по
        telegram_user_id (проект single-user, тот же приём, что
        TaskRepository.list_due_unreminded)."""
        query = select(FocusSession).where(
            FocusSession.status == IN_PROGRESS,
            FocusSession.work_ends_at <= now,
            FocusSession.work_notified_at.is_(None),
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_due_break_end(self, now: datetime) -> list[FocusSession]:
        query = select(FocusSession).where(
            FocusSession.status == ON_BREAK,
            FocusSession.break_ends_at.is_not(None),
            FocusSession.break_ends_at <= now,
            FocusSession.break_notified_at.is_(None),
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def stats_since(
        self, telegram_user_id: int, since: datetime
    ) -> tuple[int, int]:
        """(число завершённых сессий, суммарные минуты работы) с
        `since` — для карточки /ui и еженедельного дайджеста. Минуты —
        work_minutes (сам факт цикла, не то, сколько реально длилась
        сессия до отмены)."""
        query = select(
            func.count(), func.coalesce(func.sum(FocusSession.work_minutes), 0)
        ).where(
            FocusSession.telegram_user_id == telegram_user_id,
            FocusSession.status == COMPLETED,
            FocusSession.started_at >= since,
        )
        result = await self._session.execute(query)
        count, minutes = result.one()
        return count, minutes
