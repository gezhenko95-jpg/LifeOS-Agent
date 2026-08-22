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


_INSIGHT_SYSTEM_PROMPT = (
    "Ты — личный ассистент пользователя. Ниже черновик его еженедельного "
    "дайджеста (что сделано за неделю, привычки, цели). Добавь ОДНО "
    "короткое (не более 25 слов) наблюдение или вопрос на подумать на "
    "русском языке — по существу, без предисловий, без кавычек и без "
    "markdown. Верни только текст этой фразы, ничего больше."
)


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


async def _generate_insight(ai_client: AIClient, digest_text: str) -> str | None:
    messages = [
        {"role": "system", "content": _INSIGHT_SYSTEM_PROMPT},
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
) -> str:
    since = datetime.now(timezone.utc) - _WEEK

    parts = ["Итоги недели 📊", ""]
    parts.append(await _format_tasks_section(telegram_user_id, task_service, since))

    habits_section = await _format_habits_section(telegram_user_id, habit_service)
    if habits_section:
        parts.append(habits_section)

    goals_section = await _format_goals_section(telegram_user_id, goal_service)
    if goals_section:
        parts.append(goals_section)

    text = "\n".join(parts)

    if ai_client is not None:
        insight = await _generate_insight(ai_client, text)
        if insight:
            text = f"{text}\n\n💡 {_esc(insight)}"

    return text
