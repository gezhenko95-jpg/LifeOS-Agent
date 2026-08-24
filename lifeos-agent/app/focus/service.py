"""
FocusSessionService — вся бизнес-логика фокус-сессий (specs/026).
Repository — только БД, API/бот — только вызывают этот сервис.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.ownership import owned_or_none
from app.focus.models import CANCELLED, COMPLETED, IN_PROGRESS, ON_BREAK, FocusSession
from app.focus.repository import FocusSessionRepository

DEFAULT_WORK_MINUTES = 25
DEFAULT_BREAK_MINUTES = 5


class FocusSessionService:
    def __init__(self, repository: FocusSessionRepository) -> None:
        self._repository = repository

    async def start_session(
        self,
        telegram_user_id: int,
        work_minutes: int = DEFAULT_WORK_MINUTES,
        break_minutes: int = DEFAULT_BREAK_MINUTES,
        task_id: Optional[int] = None,
    ) -> FocusSession:
        if work_minutes <= 0 or break_minutes <= 0:
            raise ValueError("Длительность должна быть положительной")
        existing = await self._repository.get_active(telegram_user_id)
        if existing is not None:
            # Pomodoro по смыслу однопоточный — параллельные сессии не
            # имеют смысла (specs/026-focus-sessions.md).
            raise ValueError("Сессия уже идёт — сначала завершите или прервите её")

        now = datetime.now(timezone.utc)
        session = FocusSession(
            telegram_user_id=telegram_user_id,
            task_id=task_id,
            work_minutes=work_minutes,
            break_minutes=break_minutes,
            started_at=now,
            work_ends_at=now + timedelta(minutes=work_minutes),
            status=IN_PROGRESS,
        )
        return await self._repository.add(session)

    async def get_active_session(self, telegram_user_id: int) -> Optional[FocusSession]:
        return await self._repository.get_active(telegram_user_id)

    async def cancel_session(
        self, telegram_user_id: int, session_id: int
    ) -> Optional[FocusSession]:
        session = owned_or_none(
            await self._repository.get_by_id(session_id), telegram_user_id
        )
        if session is None or session.status not in (IN_PROGRESS, ON_BREAK):
            return None
        session.status = CANCELLED
        return await self._repository.save(session)

    async def stats_since(
        self, telegram_user_id: int, since: datetime
    ) -> tuple[int, int]:
        """(число завершённых сессий, суммарные минуты) — для /ui и
        еженедельного дайджеста."""
        return await self._repository.stats_since(telegram_user_id, since)

    # --- Опрашивающая джоба (app/telegram/jobs.py::send_focus_notifications_job) ---

    async def list_due_work_end(
        self, now: Optional[datetime] = None
    ) -> list[FocusSession]:
        return await self._repository.list_due_work_end(
            now or datetime.now(timezone.utc)
        )

    async def list_due_break_end(
        self, now: Optional[datetime] = None
    ) -> list[FocusSession]:
        return await self._repository.list_due_break_end(
            now or datetime.now(timezone.utc)
        )

    async def mark_work_notified(self, session: FocusSession) -> FocusSession:
        """Работа закончилась → перерыв. break_ends_at считается от
        work_ends_at (запланированного момента), а не от "сейчас" —
        иначе задержка опроса накапливалась бы в каждом следующем
        переходе (тот же довод, что у _maybe_create_next_occurrence
        в TaskService: серия не должна "плыть")."""
        now = datetime.now(timezone.utc)
        session.status = ON_BREAK
        session.work_notified_at = now
        session.break_ends_at = session.work_ends_at + timedelta(
            minutes=session.break_minutes
        )
        return await self._repository.save(session)

    async def mark_break_notified(self, session: FocusSession) -> FocusSession:
        session.status = COMPLETED
        session.break_notified_at = datetime.now(timezone.utc)
        return await self._repository.save(session)
