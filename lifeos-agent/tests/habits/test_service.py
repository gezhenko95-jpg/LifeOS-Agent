from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from app.habits.models import Habit, HabitLog
from app.habits.service import HabitService

TODAY = date.today()


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda habit: habit
    return repo


async def test_create_habit(repository):
    service = HabitService(repository)

    habit = await service.create_habit(telegram_user_id=1, title="Читать")

    assert habit.title == "Читать"
    assert habit.telegram_user_id == 1
    repository.add.assert_awaited_once()


async def test_create_habit_empty_title_raises(repository):
    service = HabitService(repository)

    with pytest.raises(ValueError):
        await service.create_habit(telegram_user_id=1, title="   ")


async def test_list_active_habits(repository):
    repository.list_by_user.return_value = [Habit(telegram_user_id=1, title="Читать")]
    service = HabitService(repository)

    habits = await service.list_active_habits(1)

    assert len(habits) == 1


async def test_find_active_by_title_is_case_insensitive(repository):
    repository.list_by_user.return_value = [
        Habit(telegram_user_id=1, title="Читать книгу")
    ]
    service = HabitService(repository)

    matches = await service.find_active_by_title(1, "книгу")

    assert len(matches) == 1


async def test_mark_done_today_creates_log_when_not_done_yet(repository):
    habit = Habit(telegram_user_id=1, title="Читать", id=1)
    repository.list_by_user.return_value = [habit]
    repository.has_log_on.return_value = False
    service = HabitService(repository)

    result = await service.mark_done_today(1, "читать")

    assert result is habit
    repository.add_log.assert_awaited_once_with(1, TODAY)


async def test_mark_done_today_is_idempotent(repository):
    habit = Habit(telegram_user_id=1, title="Читать", id=1)
    repository.list_by_user.return_value = [habit]
    repository.has_log_on.return_value = True
    service = HabitService(repository)

    result = await service.mark_done_today(1, "читать")

    assert result is habit
    repository.add_log.assert_not_awaited()


async def test_mark_done_today_not_found(repository):
    repository.list_by_user.return_value = []
    service = HabitService(repository)

    result = await service.mark_done_today(1, "читать")

    assert result is None
    repository.add_log.assert_not_awaited()


async def test_mark_done_by_id(repository):
    habit = Habit(telegram_user_id=1, title="Читать", id=1)
    repository.get_by_id.return_value = habit
    repository.has_log_on.return_value = False
    service = HabitService(repository)

    result = await service.mark_done_by_id(1)

    assert result is habit
    repository.add_log.assert_awaited_once_with(1, TODAY)


async def test_mark_done_by_id_not_found(repository):
    repository.get_by_id.return_value = None
    service = HabitService(repository)

    result = await service.mark_done_by_id(999)

    assert result is None


async def test_get_streak_no_logs_returns_zero(repository):
    repository.list_logs.return_value = []
    service = HabitService(repository)

    streak = await service.get_streak(1)

    assert streak == 0


async def test_get_streak_counts_consecutive_days_including_today(repository):
    repository.list_logs.return_value = [
        HabitLog(habit_id=1, completed_on=TODAY),
        HabitLog(habit_id=1, completed_on=TODAY - timedelta(days=1)),
        HabitLog(habit_id=1, completed_on=TODAY - timedelta(days=2)),
    ]
    service = HabitService(repository)

    streak = await service.get_streak(1)

    assert streak == 3


async def test_get_streak_counts_from_yesterday_if_today_not_marked_yet(repository):
    repository.list_logs.return_value = [
        HabitLog(habit_id=1, completed_on=TODAY - timedelta(days=1)),
        HabitLog(habit_id=1, completed_on=TODAY - timedelta(days=2)),
    ]
    service = HabitService(repository)

    streak = await service.get_streak(1)

    assert streak == 2


async def test_get_streak_breaks_on_gap(repository):
    repository.list_logs.return_value = [
        HabitLog(habit_id=1, completed_on=TODAY),
        HabitLog(habit_id=1, completed_on=TODAY - timedelta(days=3)),
    ]
    service = HabitService(repository)

    streak = await service.get_streak(1)

    assert streak == 1


async def test_days_since_last_completion_no_logs_returns_none(repository):
    repository.list_logs.return_value = []
    service = HabitService(repository)

    result = await service.days_since_last_completion(1)

    assert result is None


async def test_days_since_last_completion_counts_from_most_recent_log(repository):
    # list_logs сортирует desc — первый лог самый свежий
    repository.list_logs.return_value = [
        HabitLog(habit_id=1, completed_on=TODAY - timedelta(days=2)),
        HabitLog(habit_id=1, completed_on=TODAY - timedelta(days=5)),
    ]
    service = HabitService(repository)

    result = await service.days_since_last_completion(1)

    assert result == 2


async def test_delete_habit_found(repository):
    habit = Habit(telegram_user_id=1, title="Читать", id=1)
    repository.get_by_id.return_value = habit
    service = HabitService(repository)

    result = await service.delete_habit(1)

    assert result is habit
    repository.delete.assert_awaited_once_with(habit)


async def test_delete_habit_not_found(repository):
    repository.get_by_id.return_value = None
    service = HabitService(repository)

    result = await service.delete_habit(999)

    assert result is None
