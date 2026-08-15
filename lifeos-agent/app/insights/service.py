"""
Personal Insights Service (см. specs/009-personal-insights.md).

Композиция уже существующих сервисов (Tasks/Habits/Memory) — своей
таблицы нет, только чтение. Вся статистика — детерминированный код
(ADR-004), AI в этой фиче не участвует вообще.
"""

from collections import Counter
from datetime import date, datetime, timedelta, timezone

from app.habits.models import Habit
from app.habits.service import HabitService
from app.insights.calculations import (
    deadline_discipline,
    journal_habit_correlation,
    longest_streak_finding,
    productive_weekday,
)
from app.memory.service import MemoryService
from app.tasks.service import TaskService

_WINDOW_DAYS = 60


class InsightsService:
    def __init__(
        self,
        task_service: TaskService,
        habit_service: HabitService,
        memory_service: MemoryService,
    ) -> None:
        self._task_service = task_service
        self._habit_service = habit_service
        self._memory_service = memory_service

    async def build_findings(self, telegram_user_id: int) -> list[str]:
        """0..4 готовые фразы-находки, в фиксированном порядке (см. спеку)."""
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=_WINDOW_DAYS)

        completed_tasks = await self._task_service.list_tasks_completed_between(
            telegram_user_id, since, now
        )
        habits = await self._habit_service.list_active_habits(telegram_user_id)

        findings = []

        weekday_finding = productive_weekday(
            [task.completed_at for task in completed_tasks if task.completed_at]
        )
        if weekday_finding:
            findings.append(weekday_finding)

        journal_finding = await self._journal_habit_correlation(
            telegram_user_id, since, habits
        )
        if journal_finding:
            findings.append(journal_finding)

        deadline_finding = deadline_discipline(
            [
                (task.due_date, task.completed_at)
                for task in completed_tasks
                if task.due_date is not None and task.completed_at is not None
            ]
        )
        if deadline_finding:
            findings.append(deadline_finding)

        streak_finding = await self._longest_streak(habits)
        if streak_finding:
            findings.append(streak_finding)

        return findings

    async def _journal_habit_correlation(
        self, telegram_user_id: int, since: datetime, habits: list[Habit]
    ) -> str | None:
        if not habits:
            return None

        since_date = since.date()
        completed_by_habit = await self._habit_service.get_completed_days_bulk(
            [h.id for h in habits], since_date
        )
        completion_counts: Counter[date] = Counter()
        for completed_days in completed_by_habit.values():
            completion_counts.update(completed_days)

        journal_entries = await self._memory_service.list_journal_entries_since(
            telegram_user_id, since
        )
        journal_dates = {entry.created_at.date() for entry in journal_entries}

        window_days = [
            since_date + timedelta(days=offset) for offset in range(_WINDOW_DAYS)
        ]

        return journal_habit_correlation(
            window_days, journal_dates, completion_counts, len(habits)
        )

    async def _longest_streak(self, habits: list[Habit]) -> str | None:
        if not habits:
            return None

        by_id = await self._habit_service.get_longest_streaks_bulk(
            [h.id for h in habits]
        )
        streaks = {habit.title: by_id.get(habit.id, 0) for habit in habits}
        return longest_streak_finding(streaks)
