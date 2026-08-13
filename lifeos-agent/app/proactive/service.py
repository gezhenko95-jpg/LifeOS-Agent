"""
PendingPromptService — выбор следующего проактивного вопроса и хранение
состояния "открытый вопрос, ждущий ответа" (см.
specs/006-proactive-engagement.md).

Выбор категории — простой детерминированный gap-detection (ADR-004: не
нужен AI там, где хватает обычного кода): спрашиваем про то, чего у
пользователя ещё нет.
"""

import random

from app.goals.service import GoalService
from app.habits.service import HabitService
from app.memory.models import MemoryType
from app.memory.service import MemoryService
from app.proactive.models import PendingPrompt
from app.proactive.questions import (
    _MIN_PREFERENCES,
    GOAL_QUESTIONS,
    HABIT_QUESTIONS,
    PREFERENCE_QUESTIONS,
    PROJECT_QUESTIONS,
    REFLECT_QUESTIONS,
)
from app.proactive.repository import PendingPromptRepository


class PendingPromptService:
    def __init__(
        self,
        repository: PendingPromptRepository,
        goal_service: GoalService,
        habit_service: HabitService,
        memory_service: MemoryService,
    ) -> None:
        self._repository = repository
        self._goals = goal_service
        self._habits = habit_service
        self._memory = memory_service

    async def pick_and_open(self, telegram_user_id: int) -> str:
        category, question_text = await self._pick_question(telegram_user_id)
        await self._repository.upsert(telegram_user_id, category, question_text)
        return question_text

    async def get_open(self, telegram_user_id: int) -> PendingPrompt | None:
        return await self._repository.get_for_user(telegram_user_id)

    async def clear(self, telegram_user_id: int) -> None:
        await self._repository.clear_for_user(telegram_user_id)

    async def _pick_question(self, telegram_user_id: int) -> tuple[str, str]:
        goals = await self._goals.list_active_goals(telegram_user_id)
        if not goals:
            return "goal", random.choice(GOAL_QUESTIONS)

        habits = await self._habits.list_active_habits(telegram_user_id)
        if not habits:
            return "habit", random.choice(HABIT_QUESTIONS)

        projects = await self._memory.list_entries(
            telegram_user_id, type=MemoryType.PROJECT
        )
        if not projects:
            return "project", random.choice(PROJECT_QUESTIONS)

        preferences = await self._memory.list_entries(
            telegram_user_id, type=MemoryType.PREFERENCE
        )
        if len(preferences) < _MIN_PREFERENCES:
            return "preference", random.choice(PREFERENCE_QUESTIONS)

        return "reflect", random.choice(REFLECT_QUESTIONS)
