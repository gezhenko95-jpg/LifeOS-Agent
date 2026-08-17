"""
Описание и цвет задачи (миграция 017) плюс правка привычки через API.

Описание было только у привычек; теперь оно есть у задач и целей, а цвет
— способ разметить календарь по смыслу (работа/дом/здоровье).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.goals.repository import GoalRepository
from app.goals.service import GoalService
from app.tasks.models import Task
from app.tasks.repository import TaskRepository
from app.tasks.service import TaskService


@pytest.fixture
def task_service() -> TaskService:
    repository = MagicMock(spec=TaskRepository)
    repository.add = AsyncMock(side_effect=lambda task: task)
    repository.save = AsyncMock(side_effect=lambda task: task)
    return TaskService(repository)


def _task(**kwargs) -> Task:
    fields = {
        "id": 1,
        "telegram_user_id": 1,
        "title": "Купить молоко",
        "status": "active",
        "priority": "normal",
    }
    fields.update(kwargs)
    return Task(**fields)


# --- Задачи ---------------------------------------------------------------


async def test_task_can_be_created_with_description_and_color(task_service):
    task = await task_service.create_task(
        1, "Созвон", description="Обсудить смету", color="blue"
    )

    assert task.description == "Обсудить смету"
    assert task.color == "blue"


async def test_unknown_color_is_rejected(task_service):
    """Палитра фиксированная: произвольная строка из внешнего запроса не
    должна доезжать до вёрстки."""
    with pytest.raises(ValueError):
        await task_service.create_task(1, "Созвон", color="#ff0000")


async def test_color_is_case_insensitive(task_service):
    task = await task_service.create_task(1, "Созвон", color="BLUE")

    assert task.color == "blue"


async def test_empty_description_is_stored_as_none(task_service):
    task = await task_service.create_task(1, "Созвон", description="   ")

    assert task.description is None


async def test_update_sets_description_and_color(task_service):
    task_service._repository.get_by_id = AsyncMock(return_value=_task())

    updated = await task_service.update_task(1, 1, description="Детали", color="violet")

    assert updated.description == "Детали"
    assert updated.color == "violet"


async def test_empty_color_removes_the_mark(task_service):
    """Пустая строка снимает метку — иначе цвет нельзя было бы убрать."""
    task_service._repository.get_by_id = AsyncMock(return_value=_task(color="red"))

    updated = await task_service.update_task(1, 1, color="")

    assert updated.color is None


async def test_update_with_unknown_color_raises(task_service):
    task_service._repository.get_by_id = AsyncMock(return_value=_task())

    with pytest.raises(ValueError):
        await task_service.update_task(1, 1, color="ультрамарин")


async def test_description_does_not_touch_other_fields(task_service):
    task_service._repository.get_by_id = AsyncMock(
        return_value=_task(color="red", priority="high")
    )

    updated = await task_service.update_task(1, 1, description="Только детали")

    assert updated.color == "red"
    assert updated.priority == "high"


# --- Цели -----------------------------------------------------------------


@pytest.fixture
def goal_service() -> GoalService:
    repository = MagicMock(spec=GoalRepository)
    repository.save = AsyncMock(side_effect=lambda goal: goal)
    return GoalService(repository)


async def test_goal_description_can_be_set_and_cleared(goal_service):
    from app.goals.models import Goal

    goal = Goal(
        id=1, telegram_user_id=1, title="Испанский", status="active", progress=0
    )
    goal_service._repository.get_by_id = AsyncMock(return_value=goal)

    with_description = await goal_service.update_goal(1, 1, description="B1 к весне")
    assert with_description.description == "B1 к весне"

    cleared = await goal_service.update_goal(1, 1, description="  ")
    assert cleared.description is None
