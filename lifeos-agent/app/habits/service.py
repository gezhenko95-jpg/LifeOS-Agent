"""
Habits Service.

Вся бизнес-логика привычек находится здесь. Repository — только БД,
API/Conversation — только вызывают этот сервис. См. specs/004-habits.md.

Расчёт стрика (по датам) — в app/habits/streaks.py, чистые функции без
БД. Здесь только загрузка логов и раскладка в set[date]. Одиночные
методы (get_streak и т.д.) остаются для мест, где нужна ОДНА привычка
(например, сразу после mark_done); там, где привычек несколько (списки,
брифинг, дайджест, инсайты), используйте *_bulk — иначе получится N+1
запрос, по одному на привычку (см. AUDIT.md, P-1).
"""

from datetime import date
from typing import Optional

from app.core.ownership import owned_or_none
from app.habits.models import Habit
from app.habits.repository import HabitRepository
from app.habits.streaks import current_streak, days_since_last, longest_streak


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
        """Найти активные привычки пользователя по подстроке названия.

        Фильтрация — в БД (см. app/habits/repository.py, AUDIT.md P-2)."""
        query = title_query.strip()
        return await self._repository.find_active_by_title(telegram_user_id, query)

    async def mark_done_today(
        self, telegram_user_id: int, title_query: str
    ) -> Optional[Habit]:
        matches = await self.find_active_by_title(telegram_user_id, title_query)
        if not matches:
            return None
        return await self._mark_done(matches[0])

    async def mark_done_by_id(
        self, telegram_user_id: int, habit_id: int
    ) -> Optional[Habit]:
        habit = owned_or_none(
            await self._repository.get_by_id(habit_id), telegram_user_id
        )
        if habit is None:
            return None
        return await self._mark_done(habit)

    async def _mark_done(self, habit: Habit) -> Habit:
        today = date.today()
        already_done = await self._repository.has_log_on(habit.id, today)
        if not already_done:
            await self._repository.add_log(habit.id, today)
        return habit

    async def _completed_days(self, habit_id: int) -> set[date]:
        logs = await self._repository.list_logs(habit_id)
        return {log.completed_on for log in logs}

    async def _owned_ids(
        self, telegram_user_id: int, habit_ids: list[int]
    ) -> list[int]:
        """Пересечь запрошенные id с привычками, реально принадлежащими
        пользователю — один запрос, а не get_by_id в цикле (иначе
        регрессия N+1, см. AUDIT.md, P-1)."""
        owned = await self._repository.list_by_user(
            telegram_user_id, include_archived=True
        )
        owned_ids = {habit.id for habit in owned}
        return [habit_id for habit_id in habit_ids if habit_id in owned_ids]

    async def get_streak(self, telegram_user_id: int, habit_id: int) -> int:
        """Одна привычка — см. get_streaks_bulk для списка."""
        habit = owned_or_none(
            await self._repository.get_by_id(habit_id), telegram_user_id
        )
        if habit is None:
            return 0
        return current_streak(await self._completed_days(habit_id))

    async def get_streaks_bulk(
        self, telegram_user_id: int, habit_ids: list[int]
    ) -> dict[int, int]:
        """Текущий стрик для нескольких привычек одним запросом к БД
        (см. AUDIT.md, P-1). Привычка без единого лога — 0, как и у
        одиночного get_streak."""
        owned_ids = await self._owned_ids(telegram_user_id, habit_ids)
        by_habit = await self._repository.list_logs_for_habits(owned_ids)
        return {
            habit_id: current_streak(
                {log.completed_on for log in by_habit.get(habit_id, [])}
            )
            for habit_id in owned_ids
        }

    async def days_since_last_completion(
        self, telegram_user_id: int, habit_id: int
    ) -> Optional[int]:
        """Сколько дней прошло с последней отметки (None — ни разу не
        отмечалась, или привычка не найдена/не принадлежит пользователю).
        Используется нэджем "стрик прервался" (см. app/scheduler/nudges.py)."""
        habit = owned_or_none(
            await self._repository.get_by_id(habit_id), telegram_user_id
        )
        if habit is None:
            return None
        return days_since_last(await self._completed_days(habit_id))

    async def days_since_last_completion_bulk(
        self, telegram_user_id: int, habit_ids: list[int]
    ) -> dict[int, Optional[int]]:
        """Как days_since_last_completion, но для нескольких привычек
        одним запросом (см. AUDIT.md, P-1) — нэджи проверяют это условие
        для каждой активной привычки."""
        owned_ids = await self._owned_ids(telegram_user_id, habit_ids)
        by_habit = await self._repository.list_logs_for_habits(owned_ids)
        return {
            habit_id: days_since_last(
                {log.completed_on for log in by_habit.get(habit_id, [])}
            )
            for habit_id in owned_ids
        }

    async def get_longest_streak(self, telegram_user_id: int, habit_id: int) -> int:
        """Рекорд самой длинной последовательности подряд идущих дней —
        не обязательно текущей (в отличие от get_streak), а за всю
        историю логов."""
        habit = owned_or_none(
            await self._repository.get_by_id(habit_id), telegram_user_id
        )
        if habit is None:
            return 0
        return longest_streak(await self._completed_days(habit_id))

    async def get_longest_streaks_bulk(
        self, telegram_user_id: int, habit_ids: list[int]
    ) -> dict[int, int]:
        """Рекорд серии для нескольких привычек одним запросом — для
        Personal Insights (см. app/insights/service.py, AUDIT.md P-1)."""
        owned_ids = await self._owned_ids(telegram_user_id, habit_ids)
        by_habit = await self._repository.list_logs_for_habits(owned_ids)
        return {
            habit_id: longest_streak(
                {log.completed_on for log in by_habit.get(habit_id, [])}
            )
            for habit_id in owned_ids
        }

    async def get_completed_days(
        self, telegram_user_id: int, habit_id: int, since: date
    ) -> set[date]:
        """Дни (>= since), когда привычка была отмечена — для тепловой
        карты в графике дайджеста (см. app/scheduler/charts.py)."""
        habit = owned_or_none(
            await self._repository.get_by_id(habit_id), telegram_user_id
        )
        if habit is None:
            return set()
        logs = await self._repository.list_logs(habit_id)
        return {log.completed_on for log in logs if log.completed_on >= since}

    async def get_completed_days_bulk(
        self, telegram_user_id: int, habit_ids: list[int], since: date
    ) -> dict[int, set[date]]:
        """Как get_completed_days, но для нескольких привычек одним
        запросом (см. AUDIT.md, P-1) — используется графиком дайджеста и
        вечерним чек-ином, где привычки перебираются циклом."""
        owned_ids = await self._owned_ids(telegram_user_id, habit_ids)
        by_habit = await self._repository.list_logs_for_habits(owned_ids)
        return {
            habit_id: {
                log.completed_on
                for log in by_habit.get(habit_id, [])
                if log.completed_on >= since
            }
            for habit_id in owned_ids
        }

    async def delete_habit(
        self, telegram_user_id: int, habit_id: int
    ) -> Optional[Habit]:
        habit = owned_or_none(
            await self._repository.get_by_id(habit_id), telegram_user_id
        )
        if habit is None:
            return None
        await self._repository.delete(habit)
        return habit
