from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.scheduler.weekly_digest import build_weekly_digest


def _empty_habit_service() -> AsyncMock:
    service = AsyncMock()
    service.list_active_habits.return_value = []
    return service


def _empty_goal_service() -> AsyncMock:
    service = AsyncMock()
    service.list_active_goals.return_value = []
    return service


async def test_no_completed_tasks():
    task_service = AsyncMock()
    task_service.count_tasks_completed_since.return_value = 0

    text = await build_weekly_digest(
        1, task_service, _empty_habit_service(), _empty_goal_service()
    )

    assert "ни одна задача не была отмечена" in text


async def test_completed_tasks_count_and_plural_form():
    task_service = AsyncMock()
    task_service.count_tasks_completed_since.return_value = 5

    text = await build_weekly_digest(
        1, task_service, _empty_habit_service(), _empty_goal_service()
    )

    assert "Выполнено задач за неделю: 5 задач." in text


async def test_completed_tasks_singular_form():
    task_service = AsyncMock()
    task_service.count_tasks_completed_since.return_value = 1

    text = await build_weekly_digest(
        1, task_service, _empty_habit_service(), _empty_goal_service()
    )

    assert "1 задача." in text


async def test_habits_section_shows_streak():
    task_service = AsyncMock()
    task_service.count_tasks_completed_since.return_value = 0

    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = [
        SimpleNamespace(id=1, title="Читать")
    ]
    habit_service.get_streaks_bulk.return_value = {1: 4}

    text = await build_weekly_digest(
        1, task_service, habit_service, _empty_goal_service()
    )

    assert "Привычки:" in text
    assert "Читать — 🔥 4" in text


async def test_habits_section_absent_without_habits():
    task_service = AsyncMock()
    task_service.count_tasks_completed_since.return_value = 0

    text = await build_weekly_digest(
        1, task_service, _empty_habit_service(), _empty_goal_service()
    )

    assert "Привычки:" not in text


async def test_goals_section_shows_progress():
    task_service = AsyncMock()
    task_service.count_tasks_completed_since.return_value = 0

    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = [
        SimpleNamespace(title="Выучить испанский", progress=25)
    ]

    text = await build_weekly_digest(
        1, task_service, _empty_habit_service(), goal_service
    )

    assert "🎯 Выучить испанский — 25%" in text


async def test_ai_insight_appended_when_ai_client_returns_text():
    task_service = AsyncMock()
    task_service.count_tasks_completed_since.return_value = 0
    ai_client = AsyncMock()
    ai_client.complete.return_value = "  Хорошая неделя, продолжай в том же духе.  "

    text = await build_weekly_digest(
        1,
        task_service,
        _empty_habit_service(),
        _empty_goal_service(),
        ai_client=ai_client,
    )

    assert "💡 Хорошая неделя, продолжай в том же духе." in text


async def test_ai_insight_absent_without_ai_client():
    task_service = AsyncMock()
    task_service.count_tasks_completed_since.return_value = 0

    text = await build_weekly_digest(
        1, task_service, _empty_habit_service(), _empty_goal_service()
    )

    assert "💡" not in text


async def test_ai_insight_error_is_swallowed():
    from app.ai.client import AIServiceError

    task_service = AsyncMock()
    task_service.count_tasks_completed_since.return_value = 0
    ai_client = AsyncMock()
    ai_client.complete.side_effect = AIServiceError("boom")

    text = await build_weekly_digest(
        1,
        task_service,
        _empty_habit_service(),
        _empty_goal_service(),
        ai_client=ai_client,
    )

    assert "💡" not in text
    assert "ни одна задача не была отмечена" in text


async def test_ai_insight_uses_active_persona_voice():
    """specs/020-butler-personas.md."""
    from app.assistant.personas import Persona

    task_service = AsyncMock()
    task_service.count_tasks_completed_since.return_value = 0
    ai_client = AsyncMock()
    ai_client.complete.return_value = "Хороший темп."

    await build_weekly_digest(
        1,
        task_service,
        _empty_habit_service(),
        _empty_goal_service(),
        ai_client=ai_client,
        persona=Persona.DIRECTOR,
    )

    messages = ai_client.complete.call_args.args[0]
    assert "директор" in messages[0]["content"].lower()


# --- Фокус-сессии (specs/026-focus-sessions.md) -----------------------------


async def test_no_focus_service_skips_section():
    task_service = AsyncMock()
    task_service.count_tasks_completed_since.return_value = 0

    text = await build_weekly_digest(
        1, task_service, _empty_habit_service(), _empty_goal_service()
    )

    assert "🍅" not in text


async def test_focus_service_with_no_sessions_skips_section():
    task_service = AsyncMock()
    task_service.count_tasks_completed_since.return_value = 0
    focus_service = AsyncMock()
    focus_service.stats_since.return_value = (0, 0)

    text = await build_weekly_digest(
        1,
        task_service,
        _empty_habit_service(),
        _empty_goal_service(),
        focus_service=focus_service,
    )

    assert "🍅" not in text


async def test_focus_service_with_sessions_shows_stats():
    task_service = AsyncMock()
    task_service.count_tasks_completed_since.return_value = 0
    focus_service = AsyncMock()
    focus_service.stats_since.return_value = (4, 100)

    text = await build_weekly_digest(
        1,
        task_service,
        _empty_habit_service(),
        _empty_goal_service(),
        focus_service=focus_service,
    )

    assert "🍅 Фокус-сессий: 4, 100 мин." in text
