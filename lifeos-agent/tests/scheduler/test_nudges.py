from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.scheduler.nudges import build_nudges

TODAY = date.today()


def _goal(title="Цель", target_date=None, progress=50) -> SimpleNamespace:
    return SimpleNamespace(title=title, target_date=target_date, progress=progress)


def _habit(title="Привычка", id=1) -> SimpleNamespace:
    return SimpleNamespace(title=title, id=id)


async def test_no_nudges_when_nothing_to_report():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = []
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = []

    lines = await build_nudges(1, goal_service, habit_service)

    assert lines == []


async def test_goal_deadline_in_three_days():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = [
        _goal("Марафон", target_date=TODAY + timedelta(days=3), progress=40)
    ]
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = []

    lines = await build_nudges(1, goal_service, habit_service)

    assert len(lines) == 1
    assert "Марафон" in lines[0]
    assert "через 3 дн." in lines[0]
    assert "40%" in lines[0]


async def test_goal_deadline_today():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = [
        _goal("Марафон", target_date=TODAY, progress=90)
    ]
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = []

    lines = await build_nudges(1, goal_service, habit_service)

    assert len(lines) == 1
    assert "сегодня" in lines[0]


async def test_goal_deadline_outside_thresholds_not_nudged():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = [
        _goal("Марафон", target_date=TODAY + timedelta(days=10), progress=40)
    ]
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = []

    lines = await build_nudges(1, goal_service, habit_service)

    assert lines == []


async def test_goal_without_target_date_not_nudged():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = [_goal("Марафон", target_date=None)]
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = []

    lines = await build_nudges(1, goal_service, habit_service)

    assert lines == []


async def test_completed_goal_not_nudged_even_at_threshold():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = [
        _goal("Марафон", target_date=TODAY, progress=100)
    ]
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = []

    lines = await build_nudges(1, goal_service, habit_service)

    assert lines == []


async def test_habit_streak_break_nudge():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = []
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = [_habit("Читать", id=1)]
    habit_service.days_since_last_completion.return_value = 2

    lines = await build_nudges(1, goal_service, habit_service)

    assert len(lines) == 1
    assert "Читать" in lines[0]
    assert "прервался" in lines[0]


async def test_habit_streak_break_not_nudged_outside_the_day_after():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = []
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = [_habit("Читать", id=1)]
    habit_service.days_since_last_completion.return_value = 5

    lines = await build_nudges(1, goal_service, habit_service)

    assert lines == []


async def test_habit_never_completed_not_nudged():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = []
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = [_habit("Читать", id=1)]
    habit_service.days_since_last_completion.return_value = None

    lines = await build_nudges(1, goal_service, habit_service)

    assert lines == []


async def test_goal_and_habit_nudges_combined():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = [
        _goal("Марафон", target_date=TODAY + timedelta(days=1), progress=50)
    ]
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = [_habit("Читать", id=1)]
    habit_service.days_since_last_completion.return_value = 2

    lines = await build_nudges(1, goal_service, habit_service)

    assert len(lines) == 2
