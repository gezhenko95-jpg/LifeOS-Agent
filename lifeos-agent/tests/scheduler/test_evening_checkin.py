from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.scheduler.evening_checkin import build_evening_checkin_text

TODAY = date.today()


def _empty_habit_service() -> AsyncMock:
    service = AsyncMock()
    service.list_active_habits.return_value = []
    service.get_completed_days_bulk.return_value = {}
    return service


async def test_zero_completed_tasks_today():
    task_service = AsyncMock()
    task_service.count_tasks_completed_between.return_value = 0

    text = await build_evening_checkin_text(1, task_service, _empty_habit_service())

    assert "Задач выполнено: <b>0</b>" in text


async def test_completed_tasks_count_today():
    task_service = AsyncMock()
    task_service.count_tasks_completed_between.return_value = 3

    text = await build_evening_checkin_text(1, task_service, _empty_habit_service())

    assert "Задач выполнено: <b>3</b>" in text


async def test_habits_section_absent_without_habits():
    task_service = AsyncMock()
    task_service.count_tasks_completed_between.return_value = 0

    text = await build_evening_checkin_text(1, task_service, _empty_habit_service())

    assert "Привычек" not in text


async def test_habits_section_counts_done_today():
    task_service = AsyncMock()
    task_service.count_tasks_completed_between.return_value = 0

    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = [
        SimpleNamespace(id=1, title="Читать"),
        SimpleNamespace(id=2, title="Спорт"),
    ]
    # Читать отмечена сегодня, Спорт — нет
    habit_service.get_completed_days_bulk.return_value = {
        1: {TODAY},
        2: {TODAY - timedelta(days=1)},
    }

    text = await build_evening_checkin_text(1, task_service, habit_service)

    assert "Привычек отмечено: <b>1/2</b>" in text
