"""
app/scheduler/persona_nudges.py — specs/027-butler-personas-phase2.md, п.2.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.assistant.personas import Persona
from app.scheduler.persona_nudges import find_nudge_candidate, generate_nudge_text

NOW = datetime.now(timezone.utc)


def _habit(id=1, title="Бег") -> SimpleNamespace:
    return SimpleNamespace(id=id, title=title)


def _task(id=1, title="Отчёт", due_date=None) -> SimpleNamespace:
    return SimpleNamespace(id=id, title=title, due_date=due_date)


def _services(habits=None, days_since=None, tasks=None):
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = habits or []
    habit_service.days_since_last_completion_bulk.return_value = days_since or {}
    task_service = AsyncMock()
    task_service.list_active_tasks.return_value = tasks or []
    return habit_service, task_service


async def test_no_candidate_when_nothing_matches():
    habit_service, task_service = _services()

    candidate = await find_nudge_candidate(1, habit_service, task_service)

    assert candidate is None


async def test_habit_streak_break_is_a_candidate():
    habit_service, task_service = _services(
        habits=[_habit(id=1, title="Бег")], days_since={1: 2}
    )

    candidate = await find_nudge_candidate(1, habit_service, task_service)

    assert candidate is not None
    key, situation = candidate
    assert key == "habit_streak:1"
    assert "Бег" in situation


async def test_habit_not_a_candidate_outside_exact_threshold():
    """day_since == 1 или 3 — не ровно на пороге, тот же приём, что
    app/scheduler/nudges.py (day-threshold, не "<=")."""
    habit_service, task_service = _services(habits=[_habit(id=1)], days_since={1: 3})

    candidate = await find_nudge_candidate(1, habit_service, task_service)

    assert candidate is None


async def test_overdue_task_is_a_candidate_when_no_habit_matches():
    overdue_by_3 = NOW - timedelta(days=3)
    habit_service, task_service = _services(
        tasks=[_task(id=5, title="Отчёт", due_date=overdue_by_3)]
    )

    candidate = await find_nudge_candidate(1, habit_service, task_service)

    assert candidate is not None
    key, situation = candidate
    assert key == "task_overdue:5"
    assert "Отчёт" in situation


async def test_task_without_due_date_is_never_a_candidate():
    habit_service, task_service = _services(tasks=[_task(due_date=None)])

    candidate = await find_nudge_candidate(1, habit_service, task_service)

    assert candidate is None


async def test_habit_checked_before_task_when_both_match():
    overdue_by_3 = NOW - timedelta(days=3)
    habit_service, task_service = _services(
        habits=[_habit(id=1, title="Бег")],
        days_since={1: 2},
        tasks=[_task(id=5, title="Отчёт", due_date=overdue_by_3)],
    )

    candidate = await find_nudge_candidate(1, habit_service, task_service)

    assert candidate[0] == "habit_streak:1"


async def test_exclude_trigger_key_lets_a_second_slot_find_a_different_candidate():
    """Второй сегодняшний слот (см. app/telegram/jobs.py) не должен
    заново упереться в уже отправленный сегодня повод — должен найти
    ДРУГОЙ, если есть."""
    overdue_by_3 = NOW - timedelta(days=3)
    habit_service, task_service = _services(
        habits=[_habit(id=1, title="Бег")],
        days_since={1: 2},
        tasks=[_task(id=5, title="Отчёт", due_date=overdue_by_3)],
    )

    candidate = await find_nudge_candidate(
        1, habit_service, task_service, exclude_trigger_key="habit_streak:1"
    )

    assert candidate[0] == "task_overdue:5"


async def test_exclude_trigger_key_returns_none_when_no_other_candidate():
    habit_service, task_service = _services(
        habits=[_habit(id=1, title="Бег")], days_since={1: 2}
    )

    candidate = await find_nudge_candidate(
        1, habit_service, task_service, exclude_trigger_key="habit_streak:1"
    )

    assert candidate is None


async def test_generate_nudge_text_returns_stripped_ai_reply():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "  Загляни, стрик сам себя не восстановит.  "

    text = await generate_nudge_text(ai_client, "Стрик прервался.", Persona.TRAINER)

    assert text == "Загляни, стрик сам себя не восстановит."


async def test_generate_nudge_text_returns_none_on_ai_error():
    from app.ai.client import AIServiceError

    ai_client = AsyncMock()
    ai_client.complete.side_effect = AIServiceError("boom")

    text = await generate_nudge_text(ai_client, "Стрик прервался.", Persona.BUTLER)

    assert text is None
