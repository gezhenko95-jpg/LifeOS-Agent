"""
Репозиторий для задач.

Единственное место, где выполняются SQL-запросы к таблице `tasks`.
Никакой бизнес-логики — только чтение/запись.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.models import Task


class TaskRepository:
    """Доступ к таблице `tasks` через AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, task: Task) -> Task:
        self._session.add(task)
        await self._session.commit()
        await self._session.refresh(task)
        return task

    async def get_by_id(self, task_id: int) -> Optional[Task]:
        return await self._session.get(Task, task_id)

    async def list_by_user(
        self, telegram_user_id: int, status: Optional[str] = None
    ) -> list[Task]:
        query = select(Task).where(Task.telegram_user_id == telegram_user_id)
        if status is not None:
            query = query.where(Task.status == status)
        query = query.order_by(Task.created_at)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def save(self, task: Task) -> Task:
        """Сохранить изменения существующей задачи (update)."""
        await self._session.commit()
        await self._session.refresh(task)
        return task

    async def delete(self, task: Task) -> None:
        await self._session.delete(task)
        await self._session.commit()

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
