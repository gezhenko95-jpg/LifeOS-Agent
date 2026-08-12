"""
Репозиторий для целей.

Единственное место, где выполняются SQL-запросы к таблице `goals`.
Никакой бизнес-логики — только чтение/запись.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.goals.models import Goal


class GoalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, goal: Goal) -> Goal:
        self._session.add(goal)
        await self._session.commit()
        await self._session.refresh(goal)
        return goal

    async def get_by_id(self, goal_id: int) -> Optional[Goal]:
        return await self._session.get(Goal, goal_id)

    async def list_by_user(
        self, telegram_user_id: int, status: Optional[str] = None
    ) -> list[Goal]:
        query = select(Goal).where(Goal.telegram_user_id == telegram_user_id)
        if status is not None:
            query = query.where(Goal.status == status)
        query = query.order_by(Goal.created_at)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def save(self, goal: Goal) -> Goal:
        await self._session.commit()
        await self._session.refresh(goal)
        return goal

    async def delete(self, goal: Goal) -> None:
        await self._session.delete(goal)
        await self._session.commit()
