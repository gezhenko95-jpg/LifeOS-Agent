from unittest.mock import AsyncMock

import pytest

from app.tasks.models import Task
from app.tasks.service import TaskService


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda task: task
    repo.save.side_effect = lambda task: task
    return repo


async def test_create_task(repository):
    service = TaskService(repository)

    task = await service.create_task(telegram_user_id=1, title="Купить молоко")

    assert task.title == "Купить молоко"
    assert task.status == "active"
    assert task.telegram_user_id == 1
    repository.add.assert_awaited_once()


async def test_create_task_strips_title(repository):
    service = TaskService(repository)

    task = await service.create_task(telegram_user_id=1, title="  Купить молоко  ")

    assert task.title == "Купить молоко"


async def test_create_task_empty_title_raises(repository):
    service = TaskService(repository)

    with pytest.raises(ValueError):
        await service.create_task(telegram_user_id=1, title="   ")


async def test_list_active_tasks(repository):
    repository.list_by_user.return_value = [
        Task(telegram_user_id=1, title="A", status="active")
    ]
    service = TaskService(repository)

    tasks = await service.list_active_tasks(1)

    assert len(tasks) == 1
    repository.list_by_user.assert_awaited_once_with(1, status="active")


async def test_complete_task_by_title_found(repository):
    repository.list_by_user.return_value = [
        Task(telegram_user_id=1, title="Купить молоко", status="active")
    ]
    service = TaskService(repository)

    task = await service.complete_task_by_title(1, "молоко")

    assert task is not None
    assert task.status == "completed"
    repository.save.assert_awaited_once()


async def test_complete_task_by_title_sets_completed_at(repository):
    repository.list_by_user.return_value = [
        Task(telegram_user_id=1, title="Купить молоко", status="active")
    ]
    service = TaskService(repository)

    task = await service.complete_task_by_title(1, "молоко")

    assert task is not None
    assert task.completed_at is not None


async def test_complete_task_by_title_not_found(repository):
    repository.list_by_user.return_value = []
    service = TaskService(repository)

    task = await service.complete_task_by_title(1, "молоко")

    assert task is None


async def test_delete_task_by_title_found(repository):
    repository.list_by_user.return_value = [
        Task(telegram_user_id=1, title="Купить молоко", status="active")
    ]
    service = TaskService(repository)

    task = await service.delete_task_by_title(1, "молоко")

    assert task is not None
    repository.delete.assert_awaited_once()


async def test_find_active_by_title_is_case_insensitive(repository):
    repository.list_by_user.return_value = [
        Task(telegram_user_id=1, title="Купить Молоко", status="active")
    ]
    service = TaskService(repository)

    matches = await service.find_active_by_title(1, "молоко")

    assert len(matches) == 1


async def test_create_task_default_priority_is_normal(repository):
    service = TaskService(repository)

    task = await service.create_task(telegram_user_id=1, title="Купить молоко")

    assert task.priority == "normal"


async def test_create_task_with_high_priority(repository):
    service = TaskService(repository)

    task = await service.create_task(
        telegram_user_id=1, title="Позвонить в банк", priority="high"
    )

    assert task.priority == "high"


async def test_create_task_invalid_priority_raises(repository):
    service = TaskService(repository)

    with pytest.raises(ValueError):
        await service.create_task(telegram_user_id=1, title="X", priority="urgent")


async def test_list_active_tasks_sorted_by_priority(repository):
    normal_task = Task(
        telegram_user_id=1, title="Обычная", status="active", priority="normal"
    )
    high_task = Task(
        telegram_user_id=1, title="Важная", status="active", priority="high"
    )
    low_task = Task(
        telegram_user_id=1, title="Неважная", status="active", priority="low"
    )
    repository.list_by_user.return_value = [normal_task, high_task, low_task]
    service = TaskService(repository)

    tasks = await service.list_active_tasks(1)

    assert [task.title for task in tasks] == ["Важная", "Обычная", "Неважная"]


async def test_update_task_priority(repository):
    task = Task(telegram_user_id=1, title="X", status="active", priority="normal")
    repository.get_by_id.return_value = task
    service = TaskService(repository)

    updated = await service.update_task(task_id=1, priority="high")

    assert updated is not None
    assert updated.priority == "high"


async def test_update_task_invalid_priority_raises(repository):
    service = TaskService(repository)

    with pytest.raises(ValueError):
        await service.update_task(task_id=1, priority="urgent")


async def test_list_due_reminders_delegates_to_repository(repository):
    due_task = Task(telegram_user_id=1, title="X", status="active")
    repository.list_due_unreminded.return_value = [due_task]
    service = TaskService(repository)

    tasks = await service.list_due_reminders()

    assert tasks == [due_task]
    repository.list_due_unreminded.assert_awaited_once()


async def test_mark_reminded_sets_timestamp(repository):
    task = Task(telegram_user_id=1, title="X", status="active", reminded_at=None)
    repository.get_by_id.return_value = task
    service = TaskService(repository)

    updated = await service.mark_reminded(1)

    assert updated is not None
    assert updated.reminded_at is not None


async def test_mark_reminded_not_found(repository):
    repository.get_by_id.return_value = None
    service = TaskService(repository)

    result = await service.mark_reminded(999)

    assert result is None


async def test_update_task_status_to_completed_sets_completed_at(repository):
    task = Task(telegram_user_id=1, title="X", status="active")
    repository.get_by_id.return_value = task
    service = TaskService(repository)

    updated = await service.update_task(task_id=1, status="completed")

    assert updated is not None
    assert updated.completed_at is not None


async def test_update_task_status_to_active_does_not_set_completed_at(repository):
    task = Task(telegram_user_id=1, title="X", status="active")
    repository.get_by_id.return_value = task
    service = TaskService(repository)

    updated = await service.update_task(task_id=1, priority="high")

    assert updated is not None
    assert updated.completed_at is None


async def test_count_tasks_completed_since_delegates_to_repository(repository):
    from datetime import datetime, timezone

    repository.count_completed_since.return_value = 3
    service = TaskService(repository)
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)

    count = await service.count_tasks_completed_since(1, since)

    assert count == 3
    repository.count_completed_since.assert_awaited_once_with(1, since)
