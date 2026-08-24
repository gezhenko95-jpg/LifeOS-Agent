from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.scheduler.nudges import build_nudges

TODAY = date.today()
NOW = datetime.now(timezone.utc)


def _goal(title="Цель", target_date=None, progress=50) -> SimpleNamespace:
    return SimpleNamespace(title=title, target_date=target_date, progress=progress)


def _habit(title="Привычка", id=1) -> SimpleNamespace:
    return SimpleNamespace(title=title, id=id)


def _contact(
    name="Аня",
    last_contact_at=None,
    birthday_month=None,
    birthday_day=None,
    nudge_after_days=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        last_contact_at=last_contact_at or NOW,
        birthday_month=birthday_month,
        birthday_day=birthday_day,
        nudge_after_days=nudge_after_days,
    )


def _empty_goal_habit_services():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = []
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = []
    return goal_service, habit_service


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
    habit_service.days_since_last_completion_bulk.return_value = {1: 2}

    lines = await build_nudges(1, goal_service, habit_service)

    assert len(lines) == 1
    assert "Читать" in lines[0]
    assert "прервался" in lines[0]


async def test_habit_streak_break_not_nudged_outside_the_day_after():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = []
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = [_habit("Читать", id=1)]
    habit_service.days_since_last_completion_bulk.return_value = {1: 5}

    lines = await build_nudges(1, goal_service, habit_service)

    assert lines == []


async def test_habit_never_completed_not_nudged():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = []
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = [_habit("Читать", id=1)]
    habit_service.days_since_last_completion_bulk.return_value = {1: None}

    lines = await build_nudges(1, goal_service, habit_service)

    assert lines == []


async def test_goal_and_habit_nudges_combined():
    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = [
        _goal("Марафон", target_date=TODAY + timedelta(days=1), progress=50)
    ]
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = [_habit("Читать", id=1)]
    habit_service.days_since_last_completion_bulk.return_value = {1: 2}

    lines = await build_nudges(1, goal_service, habit_service)

    assert len(lines) == 2


async def test_no_contact_service_means_no_crm_nudges():
    goal_service, habit_service = _empty_goal_habit_services()

    lines = await build_nudges(1, goal_service, habit_service, contact_service=None)

    assert lines == []


async def test_stale_contact_nudge_at_exactly_thirty_days():
    goal_service, habit_service = _empty_goal_habit_services()
    contact_service = AsyncMock()
    contact_service.list_contacts.return_value = [
        _contact("Аня", last_contact_at=NOW - timedelta(days=30))
    ]

    lines = await build_nudges(1, goal_service, habit_service, contact_service)

    assert len(lines) == 1
    assert "Аня" in lines[0]
    assert "30" in lines[0]


async def test_stale_contact_not_nudged_outside_threshold():
    goal_service, habit_service = _empty_goal_habit_services()
    contact_service = AsyncMock()
    contact_service.list_contacts.return_value = [
        _contact("Аня", last_contact_at=NOW - timedelta(days=29))
    ]

    lines = await build_nudges(1, goal_service, habit_service, contact_service)

    assert lines == []


async def test_stale_contact_uses_own_threshold_when_set():
    """Своя частота нэджа (specs/018, довесок) — 14 дней вместо
    глобальных 30."""
    goal_service, habit_service = _empty_goal_habit_services()
    contact_service = AsyncMock()
    contact_service.list_contacts.return_value = [
        _contact("Аня", last_contact_at=NOW - timedelta(days=14), nudge_after_days=14)
    ]

    lines = await build_nudges(1, goal_service, habit_service, contact_service)

    assert len(lines) == 1
    assert "14" in lines[0]


async def test_stale_contact_own_threshold_ignores_global_default():
    """На 30-й день у контакта со своим порогом 14 нэдж уже не должен
    сработать повторно (условие == threshold, не >=)."""
    goal_service, habit_service = _empty_goal_habit_services()
    contact_service = AsyncMock()
    contact_service.list_contacts.return_value = [
        _contact("Аня", last_contact_at=NOW - timedelta(days=30), nudge_after_days=14)
    ]

    lines = await build_nudges(1, goal_service, habit_service, contact_service)

    assert lines == []


async def test_birthday_nudge_in_three_days():
    goal_service, habit_service = _empty_goal_habit_services()
    soon = TODAY + timedelta(days=3)
    contact_service = AsyncMock()
    contact_service.list_contacts.return_value = [
        _contact("Петя", birthday_month=soon.month, birthday_day=soon.day)
    ]

    lines = await build_nudges(1, goal_service, habit_service, contact_service)

    assert len(lines) == 1
    assert "Петя" in lines[0]
    assert "через 3 дн." in lines[0]


async def test_birthday_nudge_today():
    goal_service, habit_service = _empty_goal_habit_services()
    contact_service = AsyncMock()
    contact_service.list_contacts.return_value = [
        _contact("Петя", birthday_month=TODAY.month, birthday_day=TODAY.day)
    ]

    lines = await build_nudges(1, goal_service, habit_service, contact_service)

    assert len(lines) == 1
    assert "сегодня" in lines[0]


async def test_birthday_nudge_outside_thresholds_not_nudged():
    goal_service, habit_service = _empty_goal_habit_services()
    far = TODAY + timedelta(days=10)
    contact_service = AsyncMock()
    contact_service.list_contacts.return_value = [
        _contact("Петя", birthday_month=far.month, birthday_day=far.day)
    ]

    lines = await build_nudges(1, goal_service, habit_service, contact_service)

    assert lines == []


async def test_contact_without_birthday_not_nudged_for_birthday():
    goal_service, habit_service = _empty_goal_habit_services()
    contact_service = AsyncMock()
    contact_service.list_contacts.return_value = [_contact("Аня")]

    lines = await build_nudges(1, goal_service, habit_service, contact_service)

    assert lines == []
