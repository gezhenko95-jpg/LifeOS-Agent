"""
Репозиторий для привычек и их логов.

Единственное место, где выполняются SQL-запросы к таблицам `habits` и
`habit_logs`. Никакой бизнес-логики (расчёт стрика — в service.py).
"""

from collections import defaultdict
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.habits.models import Habit, HabitLog


def _escape_like(text: str) -> str:
    """Экранировать %, _ и сам escape-символ (см. app/tasks/repository.py
    — тот же приём, здесь не переиспользован ради избежания циклического
    импорта между доменами)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class HabitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, habit: Habit) -> Habit:
        self._session.add(habit)
        await self._session.commit()
        await self._session.refresh(habit)
        return habit

    async def get_by_id(self, habit_id: int) -> Optional[Habit]:
        return await self._session.get(Habit, habit_id)

    async def list_by_user(
        self, telegram_user_id: int, include_archived: bool = False
    ) -> list[Habit]:
        query = select(Habit).where(Habit.telegram_user_id == telegram_user_id)
        if not include_archived:
            query = query.where(Habit.archived.is_(False))
        query = query.order_by(Habit.created_at)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def find_active_by_title(
        self, telegram_user_id: int, needle: str
    ) -> list[Habit]:
        """Активные привычки, чьё название содержит needle — фильтр в БД
        (см. AUDIT.md, P-2), а не "загрузить все и отфильтровать в
        Python"."""
        query = select(Habit).where(
            Habit.telegram_user_id == telegram_user_id,
            Habit.archived.is_(False),
            Habit.title.ilike(f"%{_escape_like(needle)}%", escape="\\"),
        )
        query = query.order_by(Habit.created_at)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def delete(self, habit: Habit) -> None:
        await self._session.delete(habit)
        await self._session.commit()

    async def has_log_on(self, habit_id: int, day: date) -> bool:
        query = select(HabitLog).where(
            HabitLog.habit_id == habit_id, HabitLog.completed_on == day
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none() is not None

    async def add_log(self, habit_id: int, day: date) -> HabitLog:
        log = HabitLog(habit_id=habit_id, completed_on=day)
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        return log

    async def list_logs(self, habit_id: int) -> list[HabitLog]:
        query = (
            select(HabitLog)
            .where(HabitLog.habit_id == habit_id)
            .order_by(HabitLog.completed_on.desc())
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_logs_for_habits(
        self, habit_ids: list[int]
    ) -> dict[int, list[HabitLog]]:
        """Логи сразу для нескольких привычек, одним запросом.

        Экран со списком привычек (или брифинг/дайджест) считает стрик
        КАЖДОЙ привычки — без этого метода list_logs вызывался бы в
        цикле, по одному запросу на привычку (см. AUDIT.md, P-1). Пустой
        список на входе — пустой словарь: WHERE habit_id IN () в
        SQLAlchemy валиден, но экономим один поход к БД впустую.
        """
        if not habit_ids:
            return {}

        query = select(HabitLog).where(HabitLog.habit_id.in_(habit_ids))
        result = await self._session.execute(query)

        grouped: dict[int, list[HabitLog]] = defaultdict(list)
        for log in result.scalars():
            grouped[log.habit_id].append(log)
        return dict(grouped)
