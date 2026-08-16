"""
Репозиторий для целей.

Единственное место, где выполняются SQL-запросы к таблице `goals`.
Никакой бизнес-логики — только чтение/запись.
"""

from typing import Optional

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.goals.models import Goal


class GoalRepository(BaseRepository[Goal]):
    model = Goal

    async def list_by_user(
        self, telegram_user_id: int, status: Optional[str] = None
    ) -> list[Goal]:
        query = select(Goal).where(Goal.telegram_user_id == telegram_user_id)
        if status is not None:
            query = query.where(Goal.status == status)
        query = query.order_by(Goal.created_at)
        result = await self._session.execute(query)
        return list(result.scalars().all())
