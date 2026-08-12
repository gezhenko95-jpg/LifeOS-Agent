"""
Goals Service.

Вся бизнес-логика целей находится здесь. Repository — только БД,
API — только вызывает этот сервис. См. specs/005-goals.md.
"""

from datetime import date, datetime, timezone
from typing import Optional

from app.goals.models import Goal
from app.goals.repository import GoalRepository

ACTIVE = "active"
COMPLETED = "completed"
ABANDONED = "abandoned"

_VALID_STATUSES = {ACTIVE, COMPLETED, ABANDONED}


class GoalService:
    def __init__(self, repository: GoalRepository) -> None:
        self._repository = repository

    async def create_goal(
        self,
        telegram_user_id: int,
        title: str,
        target_date: Optional[date] = None,
    ) -> Goal:
        title = title.strip()
        if not title:
            raise ValueError("Название цели не может быть пустым")

        goal = Goal(
            telegram_user_id=telegram_user_id,
            title=title,
            target_date=target_date,
            status=ACTIVE,
            progress=0,
        )
        return await self._repository.add(goal)

    async def list_active_goals(self, telegram_user_id: int) -> list[Goal]:
        return await self._repository.list_by_user(telegram_user_id, status=ACTIVE)

    async def update_progress(self, goal_id: int, progress: int) -> Optional[Goal]:
        return await self.update_goal(goal_id, progress=progress)

    async def update_goal(
        self,
        goal_id: int,
        title: Optional[str] = None,
        target_date: Optional[date] = None,
        status: Optional[str] = None,
        progress: Optional[int] = None,
    ) -> Optional[Goal]:
        if status is not None and status not in _VALID_STATUSES:
            raise ValueError(f"Неизвестный статус: {status}")
        if progress is not None and not 0 <= progress <= 100:
            raise ValueError("Прогресс должен быть от 0 до 100")

        goal = await self._repository.get_by_id(goal_id)
        if goal is None:
            return None
        if title is not None:
            goal.title = title
        if target_date is not None:
            goal.target_date = target_date
        if status is not None:
            goal.status = status
        if progress is not None:
            goal.progress = progress
        goal.updated_at = datetime.now(timezone.utc)
        return await self._repository.save(goal)

    async def complete_goal(self, goal_id: int) -> Optional[Goal]:
        return await self.update_goal(goal_id, status=COMPLETED)

    async def delete_goal(self, goal_id: int) -> Optional[Goal]:
        goal = await self._repository.get_by_id(goal_id)
        if goal is None:
            return None
        await self._repository.delete(goal)
        return goal
