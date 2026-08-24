"""
Сборка текста еженедельного дайджеста (см. flows/007-weekly-digest.md).

По образцу app/scheduler/briefing.py: шаблонная сборка Tasks + Habits +
Goals, без снапшотов истории (ADR-004) — прогресс целей показывается
текущим, без дельты за неделю. Если передан ai_client — поверх шаблона
добавляется одна короткая AI-фраза-инсайт по итогам недели, тем же
паттерном, что и в брифинге; ошибка AI не должна сорвать отправку.
"""

import logging
from datetime import datetime, timedelta, timezone
from html import escape

from app.ai.client import AIClient, AIServiceError
from app.assistant.personas import DEFAULT_PERSONA, Persona, build_insight_prompt
from app.focus.service import FocusSessionService
from app.goals.service import GoalService
from app.habits.service import HabitService
from app.tasks.service import TaskService

logger = logging.getLogger(__name__)

_MAX_GOALS = 5
_WEEK = timedelta(days=7)


def _esc(text: str) -> str:
    """Как app/scheduler/briefing.py::_esc — сообщение уходит с
    parse_mode=HTML, любой пользовательский текст (заголовки, AI-инсайт)
    обязан пройти через это, иначе `<`/`&` в названии рвёт разбор
    HTML-сущностей и вся отправка падает (см. AUDIT.md)."""
    return escape(str(text), quote=False)


_INSIGHT_TASK_INSTRUCTION = (
    "Ниже черновик еженедельного дайджеста пользователя (что сделано за "
    "неделю, привычки, цели). Добавь наблюдение или вопрос на подумать — "
    "2-4 предложения (примерно до 70 слов), по существу и конкретно, не "
    "короткая острота. На русском языке, без предисловий, без кавычек и "
    "без markdown. Верни только текст этой вставки, ничего больше."
)


def _insight_system_prompt(persona: Persona) -> str:
    return build_insight_prompt(persona, _INSIGHT_TASK_INSTRUCTION)


async def _format_tasks_section(
    telegram_user_id: int, task_service: TaskService, since: datetime
) -> str:
    completed = await task_service.count_tasks_completed_since(telegram_user_id, since)
    if completed == 0:
        return "На этой неделе ни одна задача не была отмечена выполненной."
    word = _pluralize_tasks(completed)
    return f"Выполнено задач за неделю: {completed} {word}."


def _pluralize_tasks(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "задача"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "задачи"
    return "задач"


async def _format_habits_section(
    telegram_user_id: int, habit_service: HabitService
) -> str:
    habits = await habit_service.list_active_habits(telegram_user_id)
    if not habits:
        return ""

    streaks = await habit_service.get_streaks_bulk(
        telegram_user_id, [h.id for h in habits]
    )
    lines = ["", "Привычки:"]
    for habit in habits:
        streak = streaks.get(habit.id, 0)
        suffix = f" — 🔥 {streak}" if streak > 0 else " — пока без серии"
        lines.append(f"• {_esc(habit.title)}{suffix}")
    return "\n".join(lines)


async def _format_goals_section(
    telegram_user_id: int, goal_service: GoalService
) -> str:
    goals = await goal_service.list_active_goals(telegram_user_id)
    if not goals:
        return ""

    lines = ["", "Цели:"]
    lines.extend(
        f"🎯 {_esc(goal.title)} — {goal.progress}%" for goal in goals[:_MAX_GOALS]
    )
    return "\n".join(lines)


async def _format_focus_section(
    telegram_user_id: int, focus_service: FocusSessionService, since: datetime
) -> str:
    """specs/026-focus-sessions.md — статистика фокус-сессий за неделю.
    Пустая строка, если не завершено ни одной (та же логика, что у
    целей — раздел без данных просто не появляется, не "0 сессий")."""
    count, minutes = await focus_service.stats_since(telegram_user_id, since)
    if count == 0:
        return ""
    return f"\n🍅 Фокус-сессий: {count}, {minutes} мин."


async def _generate_insight(
    ai_client: AIClient, digest_text: str, persona: Persona
) -> str | None:
    messages = [
        {"role": "system", "content": _insight_system_prompt(persona)},
        {"role": "user", "content": digest_text},
    ]
    try:
        insight = await ai_client.complete(messages)
    except AIServiceError as exc:
        logger.warning("AI-инсайт для дайджеста не сгенерирован: %s", exc)
        return None

    insight = insight.strip()
    return insight or None


async def build_weekly_digest(
    telegram_user_id: int,
    task_service: TaskService,
    habit_service: HabitService,
    goal_service: GoalService,
    ai_client: AIClient | None = None,
    persona: Persona = DEFAULT_PERSONA,
    focus_service: FocusSessionService | None = None,
) -> str:
    """focus_service=None тихо пропускает раздел фокус-сессий — тот же
    паттерн опциональности, что у ai_client/у ConversationEngine."""
    since = datetime.now(timezone.utc) - _WEEK

    parts = ["Итоги недели 📊", ""]
    parts.append(await _format_tasks_section(telegram_user_id, task_service, since))

    habits_section = await _format_habits_section(telegram_user_id, habit_service)
    if habits_section:
        parts.append(habits_section)

    goals_section = await _format_goals_section(telegram_user_id, goal_service)
    if goals_section:
        parts.append(goals_section)

    if focus_service is not None:
        focus_section = await _format_focus_section(
            telegram_user_id, focus_service, since
        )
        if focus_section:
            parts.append(focus_section)

    text = "\n".join(parts)

    if ai_client is not None:
        insight = await _generate_insight(ai_client, text, persona)
        if insight:
            text = f"{text}\n\n💡 {_esc(insight)}"

    return text
