"""
Habits Service.

Вся бизнес-логика привычек (в т.ч. расчёт стрика) находится здесь.
Repository — только БД, API/Conversation — только вызывают этот сервис.
См. specs/004-habits.md.
"""

from datetime import date, timedelta
from typing import Optional

from app.habits.models import Habit
from app.habits.repository import HabitRepository


class HabitService:
    def __init__(self, repository: HabitRepository) -> None:
        self._repository = repository

    async def create_habit(self, telegram_user_id: int, title: str) -> Habit:
        title = title.strip()
        if not title:
            raise ValueError("Название привычки не может быть пустым")

        habit = Habit(telegram_user_id=telegram_user_id, title=title)
        return await self._repository.add(habit)

    async def list_active_habits(self, telegram_user_id: int) -> list[Habit]:
        return await self._repository.list_by_user(telegram_user_id)

    async def find_active_by_title(
        self, telegram_user_id: int, title_query: str
    ) -> list[Habit]:
        """Найти активные привычки пользователя по подстроке названия."""
        query = title_query.strip().lower()
        habits = await self.list_active_habits(telegram_user_id)
        return [habit for habit in habits if query in habit.title.lower()]

    async def mark_done_today(
        self, telegram_user_id: int, title_query: str
    ) -> Optional[Habit]:
        matches = await self.find_active_by_title(telegram_user_id, title_query)
        if not matches:
            return None
        return await self._mark_done(matches[0])

    async def mark_done_by_id(self, habit_id: int) -> Optional[Habit]:
        habit = await self._repository.get_by_id(habit_id)
        if habit is None:
            return None
        return await self._mark_done(habit)

    async def _mark_done(self, habit: Habit) -> Habit:
        today = date.today()
        already_done = await self._repository.has_log_on(habit.id, today)
        if not already_done:
            await self._repository.add_log(habit.id, today)
        return habit

    async def get_streak(self, habit_id: int) -> int:
        """Сколько дней подряд выполнялась привычка, включая сегодня.

        Если сегодня ещё не отмечено — стрик считается с вчерашнего дня,
        чтобы серия не обрывалась только потому, что день не закончился.
        """
        logs = await self._repository.list_logs(habit_id)
        completed_days = {log.completed_on for log in logs}
        if not completed_days:
            return 0

        cursor = date.today()
        if cursor not in completed_days:
            cursor -= timedelta(days=1)

        streak = 0
        while cursor in completed_days:
            streak += 1
            cursor -= timedelta(days=1)

        return streak

    async def delete_habit(self, habit_id: int) -> Optional[Habit]:
        habit = await self._repository.get_by_id(habit_id)
        if habit is None:
            return None
        await self._repository.delete(habit)
        return habit
