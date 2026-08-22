from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.tasks.models import Task
from app.tasks.service import TaskService


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda task: task
    repo.save.side_effect = lambda task: task
    # Реальная фильтрация теперь в БД (см. app/tasks/repository.py,
    # AUDIT.md P-2) — здесь repository замокан, поэтому имитируем ровно
    # то поведение, которое раньше жило в TaskService.find_active_by_title
    # (substring, case-insensitive), читая из list_by_user.return_value в
    # МОМЕНТ ВЫЗОВА (не при создании фикстуры — тесты настраивают
    # list_by_user уже после получения фикстуры). Настоящая SQL-версия
    # проверяется отдельно, против SQLite: tests/tasks/test_repository.py.
    repo.find_active_by_title.side_effect = lambda telegram_user_id, query: [
        task
        for task in repo.list_by_user.return_value
        if query.lower() in task.title.lower()
    ]
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

    updated = await service.update_task(1, task_id=1, priority="high")

    assert updated is not None
    assert updated.priority == "high"


async def test_update_task_invalid_priority_raises(repository):
    service = TaskService(repository)

    with pytest.raises(ValueError):
        await service.update_task(1, task_id=1, priority="urgent")


async def test_update_task_wrong_owner_returns_none(repository):
    task = Task(telegram_user_id=1, title="X", status="active", priority="normal")
    repository.get_by_id.return_value = task
    service = TaskService(repository)

    updated = await service.update_task(2, task_id=1, priority="high")

    assert updated is None


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

    updated = await service.mark_reminded(1, 1)

    assert updated is not None
    assert updated.reminded_at is not None


async def test_mark_reminded_not_found(repository):
    repository.get_by_id.return_value = None
    service = TaskService(repository)

    result = await service.mark_reminded(1, 999)

    assert result is None


async def test_mark_reminded_wrong_owner_returns_none(repository):
    task = Task(telegram_user_id=1, title="X", status="active", reminded_at=None)
    repository.get_by_id.return_value = task
    service = TaskService(repository)

    result = await service.mark_reminded(2, 1)

    assert result is None


async def test_update_task_status_to_completed_sets_completed_at(repository):
    task = Task(telegram_user_id=1, title="X", status="active")
    repository.get_by_id.return_value = task
    service = TaskService(repository)

    updated = await service.update_task(1, task_id=1, status="completed")

    assert updated is not None
    assert updated.completed_at is not None


async def test_update_task_status_to_active_does_not_set_completed_at(repository):
    task = Task(telegram_user_id=1, title="X", status="active")
    repository.get_by_id.return_value = task
    service = TaskService(repository)

    updated = await service.update_task(1, task_id=1, priority="high")

    assert updated is not None
    assert updated.completed_at is None


async def test_count_tasks_completed_since_delegates_to_repository(repository):
    repository.count_completed_since.return_value = 3
    service = TaskService(repository)
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)

    count = await service.count_tasks_completed_since(1, since)

    assert count == 3
    repository.count_completed_since.assert_awaited_once_with(1, since)


async def test_count_tasks_completed_between_delegates_to_repository(repository):
    repository.count_completed_between.return_value = 2
    service = TaskService(repository)
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)
    until = datetime(2026, 8, 8, tzinfo=timezone.utc)

    count = await service.count_tasks_completed_between(1, since, until)

    assert count == 2
    repository.count_completed_between.assert_awaited_once_with(1, since, until)


async def test_list_tasks_completed_between_delegates_to_repository(repository):
    completed_task = Task(id=1, telegram_user_id=1, title="X", status="completed")
    repository.list_completed_between.return_value = [completed_task]
    service = TaskService(repository)
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)
    until = datetime(2026, 8, 8, tzinfo=timezone.utc)

    tasks = await service.list_tasks_completed_between(1, since, until)

    assert tasks == [completed_task]
    repository.list_completed_between.assert_awaited_once_with(1, since, until)


# --- Recurring tasks ---------------------------------------------------


def _dt(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


async def test_create_task_with_recurrence_and_due_date(repository):
    service = TaskService(repository)

    task = await service.create_task(
        telegram_user_id=1,
        title="Оплатить интернет",
        due_date=_dt(2026, 8, 17),
        recurrence="weekly",
    )

    assert task.recurrence == "weekly"
    assert task.due_date == _dt(2026, 8, 17)


async def test_create_task_with_recurrence_without_due_date_gets_auto_date(
    repository,
):
    service = TaskService(repository)

    task = await service.create_task(
        telegram_user_id=1, title="Пить воду", recurrence="daily"
    )

    assert task.recurrence == "daily"
    assert task.due_date is not None


async def test_create_task_invalid_recurrence_raises(repository):
    service = TaskService(repository)

    with pytest.raises(ValueError):
        await service.create_task(telegram_user_id=1, title="X", recurrence="yearly")


async def test_complete_recurring_task_creates_next_daily_occurrence(repository):
    repository.list_by_user.return_value = [
        Task(
            telegram_user_id=1,
            title="Пить таблетки",
            status="active",
            due_date=_dt(2026, 8, 13),
            recurrence="daily",
        )
    ]
    service = TaskService(repository)

    await service.complete_task_by_title(1, "таблетки")

    assert repository.add.await_count == 1
    next_task = repository.add.await_args.args[0]
    assert next_task.due_date == _dt(2026, 8, 14)
    assert next_task.status == "active"
    assert next_task.recurrence == "daily"
    assert next_task.title == "Пить таблетки"


async def test_complete_recurring_task_weekly(repository):
    repository.list_by_user.return_value = [
        Task(
            telegram_user_id=1,
            title="Оплатить интернет",
            status="active",
            due_date=_dt(2026, 8, 17),
            recurrence="weekly",
        )
    ]
    service = TaskService(repository)

    await service.complete_task_by_title(1, "интернет")

    next_task = repository.add.await_args.args[0]
    assert next_task.due_date == _dt(2026, 8, 24)


async def test_complete_recurring_task_monthly_clamps_month_end(repository):
    repository.list_by_user.return_value = [
        Task(
            telegram_user_id=1,
            title="Отчёт",
            status="active",
            due_date=_dt(2026, 1, 31),
            recurrence="monthly",
        )
    ]
    service = TaskService(repository)

    await service.complete_task_by_title(1, "отчёт")

    next_task = repository.add.await_args.args[0]
    assert next_task.due_date == _dt(2026, 2, 28)


async def test_complete_non_recurring_task_does_not_create_next_occurrence(
    repository,
):
    repository.list_by_user.return_value = [
        Task(telegram_user_id=1, title="Купить молоко", status="active")
    ]
    service = TaskService(repository)

    await service.complete_task_by_title(1, "молоко")

    repository.add.assert_not_awaited()


async def test_update_task_to_completed_also_creates_next_occurrence(repository):
    task = Task(
        telegram_user_id=1,
        title="Пить воду",
        status="active",
        due_date=_dt(2026, 8, 13),
        recurrence="daily",
    )
    repository.get_by_id.return_value = task
    service = TaskService(repository)

    await service.update_task(1, task_id=1, status="completed")

    next_task = repository.add.await_args.args[0]
    assert next_task.due_date == _dt(2026, 8, 14)


async def test_update_task_invalid_recurrence_raises(repository):
    service = TaskService(repository)

    with pytest.raises(ValueError):
        await service.update_task(1, task_id=1, recurrence="yearly")
