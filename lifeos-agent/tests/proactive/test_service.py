"""
Тесты gap-detection приоритета в PendingPromptService (см.
specs/006-proactive-engagement.md). Репозитории/сервисы — AsyncMock, без
реальной БД (по образцу tests/habits/test_service.py).
"""

from unittest.mock import AsyncMock

from app.proactive.questions import (
    GOAL_QUESTIONS,
    HABIT_QUESTIONS,
    PREFERENCE_QUESTIONS,
    PROJECT_QUESTIONS,
    REFLECT_QUESTIONS,
)
from app.proactive.service import PendingPromptService


def _service(goals=None, habits=None, projects=None, preferences=None):
    repository = AsyncMock()
    repository.upsert.side_effect = lambda uid, category, text: AsyncMock(
        category=category, question_text=text
    )

    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = goals or []

    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = habits or []

    memory_service = AsyncMock()

    def _list_entries(telegram_user_id, type=None):
        from app.memory.models import MemoryType

        if type is MemoryType.PROJECT:
            return projects or []
        if type is MemoryType.PREFERENCE:
            return preferences or []
        return []

    memory_service.list_entries.side_effect = _list_entries

    return (
        PendingPromptService(repository, goal_service, habit_service, memory_service),
        repository,
    )


async def test_no_goals_asks_goal_question():
    service, repository = _service()

    question = await service.pick_and_open(1)

    assert question in GOAL_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "goal", question)


async def test_has_goals_but_no_habits_asks_habit_question():
    service, repository = _service(goals=[object()])

    question = await service.pick_and_open(1)

    assert question in HABIT_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "habit", question)


async def test_has_goals_and_habits_but_no_projects_asks_project_question():
    service, repository = _service(goals=[object()], habits=[object()])

    question = await service.pick_and_open(1)

    assert question in PROJECT_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "project", question)


async def test_fewer_than_three_preferences_asks_preference_question():
    service, repository = _service(
        goals=[object()],
        habits=[object()],
        projects=[object()],
        preferences=[object(), object()],
    )

    question = await service.pick_and_open(1)

    assert question in PREFERENCE_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "preference", question)


async def test_everything_filled_asks_reflect_question():
    service, repository = _service(
        goals=[object()],
        habits=[object()],
        projects=[object()],
        preferences=[object(), object(), object()],
    )

    question = await service.pick_and_open(1)

    assert question in REFLECT_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "reflect", question)


async def test_get_open_delegates_to_repository():
    service, repository = _service()
    repository.get_for_user.return_value = "pending"

    result = await service.get_open(1)

    assert result == "pending"
    repository.get_for_user.assert_awaited_once_with(1)


async def test_clear_delegates_to_repository():
    service, repository = _service()

    await service.clear(1)

    repository.clear_for_user.assert_awaited_once_with(1)
