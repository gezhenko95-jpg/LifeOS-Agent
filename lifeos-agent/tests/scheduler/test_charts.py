from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.scheduler.charts import ChartData, gather_chart_data, render_chart

TODAY = date.today()

# --- render_chart (чистая функция, без БД) ------------------------------


def test_render_chart_none_when_nothing_to_show():
    data = ChartData(
        weekly_task_counts=[("06.07", 0), ("13.07", 0)],
        habit_series=[],
    )

    assert render_chart(data) is None


def test_render_chart_with_task_activity_returns_png():
    data = ChartData(
        weekly_task_counts=[("06.07", 2), ("13.07", 5)],
        habit_series=[],
    )

    buf = render_chart(data)

    assert buf is not None
    assert buf.read(8)[:4] == b"\x89PNG"


def test_render_chart_with_only_habits_returns_png():
    data = ChartData(
        weekly_task_counts=[("06.07", 0), ("13.07", 0)],
        habit_series=[("Читать", [True, False, True])],
    )

    buf = render_chart(data)

    assert buf is not None
    assert buf.read(8)[:4] == b"\x89PNG"


def test_render_chart_handles_single_week_and_habit():
    # Крайний случай для matplotlib-осей — не должно падать
    data = ChartData(
        weekly_task_counts=[("13.08", 1)],
        habit_series=[("Читать", [True])],
    )

    buf = render_chart(data)

    assert buf is not None


def test_render_chart_many_habits_does_not_crash():
    data = ChartData(
        weekly_task_counts=[("06.07", 3)],
        habit_series=[(f"Привычка {i}", [True, False] * 15) for i in range(5)],
    )

    buf = render_chart(data)

    assert buf is not None


# --- gather_chart_data (нужны сервисы) -----------------------------------


async def test_gather_weekly_counts_has_six_weeks_oldest_to_newest():
    task_service = AsyncMock()
    task_service.count_tasks_completed_between.side_effect = [1, 2, 3, 4, 5, 6]
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = []

    data = await gather_chart_data(1, task_service, habit_service)

    assert len(data.weekly_task_counts) == 6
    assert [count for _, count in data.weekly_task_counts] == [1, 2, 3, 4, 5, 6]
    assert task_service.count_tasks_completed_between.await_count == 6


async def test_gather_habit_series_has_thirty_days_per_habit():
    task_service = AsyncMock()
    task_service.count_tasks_completed_between.return_value = 0
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = [
        SimpleNamespace(id=1, title="Читать")
    ]
    habit_service.get_completed_days.return_value = {TODAY, TODAY - timedelta(days=2)}

    data = await gather_chart_data(1, task_service, habit_service)

    assert len(data.habit_series) == 1
    title, days = data.habit_series[0]
    assert title == "Читать"
    assert len(days) == 30
    assert days[-1] is True  # последний день — сегодня, отмечено
    assert days[-3] is True  # позавчера — тоже отмечено
    assert days[-2] is False  # вчера — не отмечено


async def test_gather_no_habits_gives_empty_series():
    task_service = AsyncMock()
    task_service.count_tasks_completed_between.return_value = 0
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = []

    data = await gather_chart_data(1, task_service, habit_service)

    assert data.habit_series == []
