"""
Репозиторий для задач.

Единственное место, где выполняются SQL-запросы к таблице `tasks`.
Никакой бизнес-логики — только чтение/запись.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select

from app.core.repository import BaseRepository, escape_like
from app.tasks.models import Task


class TaskRepository(BaseRepository[Task]):
    """Доступ к таблице `tasks` через AsyncSession."""

    model = Task

    async def list_by_user(
        self, telegram_user_id: int, status: Optional[str] = None
    ) -> list[Task]:
        query = select(Task).where(Task.telegram_user_id == telegram_user_id)
        if status is not None:
            query = query.where(Task.status == status)
        query = query.order_by(Task.created_at)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def find_active_by_title(
        self, telegram_user_id: int, needle: str
    ) -> list[Task]:
        """Активные задачи, чьё название содержит needle — фильтр в БД
        (см. AUDIT.md, P-2), а не "загрузить все активные и отфильтровать
        в Python". Порядок — created_at, как у list_by_user; приоритетную
        пересортировку делает TaskService (набор совпадений маленький,
        сортировать его в Python дёшево)."""
        query = select(Task).where(
            Task.telegram_user_id == telegram_user_id,
            Task.status == "active",
            Task.title.ilike(f"%{escape_like(needle)}%", escape="\\"),
        )
        query = query.order_by(Task.created_at)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_due_unreminded(self, now: datetime) -> list[Task]:
        """Активные задачи с наступившим сроком, по которым ещё не напомнили."""
        query = select(Task).where(
            Task.status == "active",
            Task.due_date.is_not(None),
            Task.due_date <= now,
            Task.reminded_at.is_(None),
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count_completed_since(
        self, telegram_user_id: int, since: datetime
    ) -> int:
        """Сколько задач пользователя завершено, начиная с `since`.

        Без фильтра по telegram_user_id не обойтись здесь (в отличие от
        list_due_unreminded) — дайджест персональный, а не общесистемный.
        """
        query = select(func.count()).where(
            Task.telegram_user_id == telegram_user_id,
            Task.status == "completed",
            Task.completed_at.is_not(None),
            Task.completed_at >= since,
        )
        result = await self._session.execute(query)
        return result.scalar_one()

    async def count_completed_between(
        self, telegram_user_id: int, since: datetime, until: datetime
    ) -> int:
        """Сколько задач завершено в полуоткрытом интервале [since, until) —
        для графика "по неделям" (см. app/scheduler/charts.py)."""
        query = select(func.count()).where(
            Task.telegram_user_id == telegram_user_id,
            Task.status == "completed",
            Task.completed_at.is_not(None),
            Task.completed_at >= since,
            Task.completed_at < until,
        )
        result = await self._session.execute(query)
        return result.scalar_one()

    async def list_completed_between(
        self, telegram_user_id: int, since: datetime, until: datetime
    ) -> list[Task]:
        """Как count_completed_between, но возвращает сами задачи — нужны
        completed_at/due_date для находок Personal Insights
        (см. app/insights/service.py, specs/009-personal-insights.md)."""
        query = select(Task).where(
            Task.telegram_user_id == telegram_user_id,
            Task.status == "completed",
            Task.completed_at.is_not(None),
            Task.completed_at >= since,
            Task.completed_at < until,
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())
