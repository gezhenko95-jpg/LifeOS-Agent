from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.ai.client import AIServiceError
from app.memory.models import MemoryEntry
from app.scheduler.briefing import build_morning_briefing
from app.tasks.models import Task

TODAY = date.today()


def _task(title: str, due_date: date | None = None, priority: str = "normal") -> Task:
    due = datetime.combine(due_date, datetime.min.time()) if due_date else None
    return Task(telegram_user_id=1, title=title, due_date=due, priority=priority)


def _memory(content: str, type_: str) -> MemoryEntry:
    return MemoryEntry(telegram_user_id=1, type=type_, content=content, source="manual")


def _empty_habit_service() -> AsyncMock:
    service = AsyncMock()
    service.list_active_habits.return_value = []
    return service


def _empty_goal_service() -> AsyncMock:
    service = AsyncMock()
    service.list_active_goals.return_value = []
    return service


async def test_no_tasks_and_no_memory():
    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = []
    memory_service = AsyncMock()
    memory_service.list_entries.return_value = []

    text = await build_morning_briefing(
        1,
        task_service,
        memory_service,
        _empty_habit_service(),
        _empty_goal_service(),
    )

    assert "Активных задач нет" in text
    assert "Цели" not in text and "Проекты" not in text


async def test_main_task_is_todays_task_and_sections_split_correctly():
    today_task = _task("Позвонить маме", TODAY)
    overdue_task = _task("Сдать отчет", TODAY - timedelta(days=3))
    upcoming_task = _task("Купить билеты", TODAY + timedelta(days=5))

    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = [
        overdue_task,
        today_task,
        upcoming_task,
    ]
    memory_service = AsyncMock()
    memory_service.list_entries.return_value = [_memory("LifeOS Agent", "project")]

    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = [
        SimpleNamespace(title="Выучить английский", progress=40)
    ]

    text = await build_morning_briefing(
        1, task_service, memory_service, _empty_habit_service(), goal_service
    )

    assert "Главное на сегодня" in text and "Позвонить маме" in text
    assert "Дальше" in text
    assert "Купить билеты" in text
    assert "Просрочено" in text
    assert "Сдать отчет" in text
    # просроченная задача не должна попасть в раздел "Дальше"
    lines = text.splitlines()
    rest_index = next(i for i, ln in enumerate(lines) if "Дальше" in ln)
    overdue_index = next(i for i, ln in enumerate(lines) if "Просрочено" in ln)
    assert not any("Сдать отчет" in ln for ln in lines[rest_index:overdue_index])
    assert "Выучить английский" in text and "40%" in text
    assert "LifeOS Agent" in text


async def test_main_task_falls_back_to_overdue_and_is_not_duplicated():
    overdue_task = _task("Сдать отчет", TODAY - timedelta(days=1))

    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = [overdue_task]
    memory_service = AsyncMock()
    memory_service.list_entries.return_value = []

    text = await build_morning_briefing(
        1,
        task_service,
        memory_service,
        _empty_habit_service(),
        _empty_goal_service(),
    )

    assert "Главное на сегодня" in text and "Сдать отчет" in text
    assert "Просрочено" not in text


async def test_main_task_falls_back_to_upcoming_when_no_today_or_overdue():
    upcoming_task = _task("Купить билеты", TODAY + timedelta(days=2))
    no_date_task = _task("Прочитать книгу", None)

    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = [upcoming_task, no_date_task]
    memory_service = AsyncMock()
    memory_service.list_entries.return_value = []

    text = await build_morning_briefing(
        1,
        task_service,
        memory_service,
        _empty_habit_service(),
        _empty_goal_service(),
    )

    assert "Главное на сегодня" in text and "Купить билеты" in text
    assert "Дальше" in text
    assert "Прочитать книгу" in text


async def test_main_task_prefers_high_priority_task_from_today():
    # TaskService.list_active_tasks уже сортирует high -> normal -> low
    # (см. tests/tasks/test_service.py); брифинг просто берёт первую
    # задачу "на сегодня" из уже отсортированного списка.
    high_today = _task("Позвонить в банк", TODAY, priority="high")
    normal_today = _task("Купить молоко", TODAY, priority="normal")

    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = [high_today, normal_today]
    memory_service = AsyncMock()
    memory_service.list_entries.return_value = []

    text = await build_morning_briefing(
        1,
        task_service,
        memory_service,
        _empty_habit_service(),
        _empty_goal_service(),
    )

    assert "Главное на сегодня" in text and "Позвонить в банк" in text
    assert "Купить молоко" in text


async def test_goals_and_projects_section_absent_when_empty():
    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = [_task("Купить молоко", TODAY)]
    memory_service = AsyncMock()
    memory_service.list_entries.return_value = []

    text = await build_morning_briefing(
        1,
        task_service,
        memory_service,
        _empty_habit_service(),
        _empty_goal_service(),
    )

    assert "Цели" not in text and "Проекты" not in text


async def test_goals_section_uses_goal_service_with_progress():
    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = []
    memory_service = AsyncMock()
    memory_service.list_entries.return_value = []

    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = [
        SimpleNamespace(title="Пробежать марафон", progress=15)
    ]

    text = await build_morning_briefing(
        1, task_service, memory_service, _empty_habit_service(), goal_service
    )

    assert "Пробежать марафон" in text and "15%" in text


async def test_habits_section_shows_streak():
    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = []
    memory_service = AsyncMock()
    memory_service.list_entries.return_value = []

    # Привычка — простой объект с id/title, стрик считает HabitService.
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = [
        SimpleNamespace(id=1, title="Читать")
    ]
    habit_service.get_streaks_bulk.return_value = {1: 5}

    text = await build_morning_briefing(
        1, task_service, memory_service, habit_service, _empty_goal_service()
    )

    assert "Привычки" in text
    assert "Читать" in text and "🔥 5" in text


async def test_habits_section_absent_without_habits():
    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = []
    memory_service = AsyncMock()
    memory_service.list_entries.return_value = []

    text = await build_morning_briefing(
        1,
        task_service,
        memory_service,
        _empty_habit_service(),
        _empty_goal_service(),
    )

    assert "Привычки" not in text


async def test_ai_insight_appended_when_ai_client_returns_text():
    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = []
    memory_service = AsyncMock()
    memory_service.list_entries.return_value = []

    ai_client = AsyncMock()
    ai_client.complete.return_value = "  Начните с самого сложного дела.  "

    text = await build_morning_briefing(
        1,
        task_service,
        memory_service,
        _empty_habit_service(),
        _empty_goal_service(),
        ai_client=ai_client,
    )

    assert "💡 <i>Начните с самого сложного дела.</i>" in text
    ai_client.complete.assert_awaited_once()


async def test_ai_insight_absent_without_ai_client():
    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = []
    memory_service = AsyncMock()
    memory_service.list_entries.return_value = []

    text = await build_morning_briefing(
        1,
        task_service,
        memory_service,
        _empty_habit_service(),
        _empty_goal_service(),
    )

    assert "💡" not in text


async def test_ai_insight_error_is_swallowed_and_briefing_still_sent():
    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = []
    memory_service = AsyncMock()
    memory_service.list_entries.return_value = []

    ai_client = AsyncMock()
    ai_client.complete.side_effect = AIServiceError("boom")

    text = await build_morning_briefing(
        1,
        task_service,
        memory_service,
        _empty_habit_service(),
        _empty_goal_service(),
        ai_client=ai_client,
    )

    assert "Активных задач нет" in text
    assert "💡" not in text


async def test_ai_insight_empty_response_is_ignored():
    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = []
    memory_service = AsyncMock()
    memory_service.list_entries.return_value = []

    ai_client = AsyncMock()
    ai_client.complete.return_value = "   "

    text = await build_morning_briefing(
        1,
        task_service,
        memory_service,
        _empty_habit_service(),
        _empty_goal_service(),
        ai_client=ai_client,
    )

    assert "💡" not in text
