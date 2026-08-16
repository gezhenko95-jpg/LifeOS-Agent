"""
Сборка текста утреннего брифинга (см. flows/001-morning-briefing.md).

Основа — шаблонная сборка Tasks + Memory + Habits + Goals (без AI).
Если передан ai_client (ключ OpenRouter задан, см. app/ai/client.py),
поверх шаблона добавляется одна короткая AI-фраза-инсайт по уже
собранному контексту. Ошибка AI никогда не должна сорвать отправку
брифинга — при сбое инсайт просто не добавляется (см. _generate_insight).

Оформление: HTML (parse_mode задаётся при отправке, см.
app/telegram/jobs.py). Всё пользовательское проходит через escape —
задача с названием «<b>» иначе сломала бы разметку всего сообщения.
"""

import logging
from datetime import date
from html import escape

from app.ai.client import AIClient, AIServiceError
from app.goals.models import Goal
from app.goals.service import GoalService
from app.habits.models import Habit
from app.habits.service import HabitService
from app.memory.models import MemoryEntry, MemoryType
from app.memory.service import MemoryService
from app.tasks.formatting import format_due_human, task_status_emoji
from app.tasks.models import Task
from app.tasks.service import TaskService

logger = logging.getLogger(__name__)

_MAX_MEMORY_ITEMS = 3
_DIVIDER = "━━━━━━━━━━━━━━━"

_MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
_WEEKDAYS_NOMINATIVE = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)

_INSIGHT_SYSTEM_PROMPT = (
    "Ты — личный ассистент пользователя. Ниже черновик его утреннего "
    "брифинга (задачи, привычки, цели). Добавь ОДНО короткое (не более "
    "20 слов) персональное наблюдение или совет на русском языке — по "
    "существу, без предисловий, без кавычек и без markdown. Верни только "
    "текст этой фразы, ничего больше."
)


def _esc(text: str) -> str:
    return escape(str(text), quote=False)


def format_today(today: date) -> str:
    """«пятница, 15 августа» — дата словами.

    Брифинг приходит каждое утро и легко сливается со вчерашним; строка
    с днём недели сразу говорит, к какому дню он относится.
    """
    return (
        f"{_WEEKDAYS_NOMINATIVE[today.weekday()]}, "
        f"{today.day} {_MONTHS_GENITIVE[today.month - 1]}"
    )


def _split_tasks(
    tasks: list[Task], today: date
) -> tuple[list[Task], list[Task], list[Task]]:
    """Разделить активные задачи на просроченные / на сегодня / остальные."""
    overdue: list[Task] = []
    today_tasks: list[Task] = []
    upcoming: list[Task] = []

    for task in tasks:
        if task.due_date is None:
            upcoming.append(task)
        elif task.due_date.date() < today:
            overdue.append(task)
        elif task.due_date.date() == today:
            today_tasks.append(task)
        else:
            upcoming.append(task)

    return overdue, today_tasks, upcoming


def _pick_main_task(
    overdue: list[Task], today_tasks: list[Task], upcoming: list[Task]
) -> Task | None:
    if today_tasks:
        return today_tasks[0]
    if overdue:
        return overdue[0]
    if upcoming:
        return upcoming[0]
    return None


def _format_task_line(task: Task, in_overdue_section: bool = False) -> str:
    if not task.due_date:
        return f"   {task_status_emoji(task)} {_esc(task.title)}"
    when = format_due_human(task.due_date)
    if in_overdue_section:
        # Раздел уже называется «Просрочено» — повторять это в каждой
        # строке незачем.
        when = when.replace(" (просрочено)", "")
    return f"   {task_status_emoji(task)} {_esc(task.title)} · {when}"


def _format_tasks_section(tasks: list[Task], today: date) -> str:
    lines = ["☀️ <b>Доброе утро!</b>", f"<i>{format_today(today)}</i>"]

    overdue, today_tasks, upcoming = _split_tasks(tasks, today)
    main_task = _pick_main_task(overdue, today_tasks, upcoming)

    if main_task is None:
        lines.append("")
        lines.append(_DIVIDER)
        lines.append("Активных задач нет — день ваш. 🌤")
        return "\n".join(lines)

    lines.append("")
    lines.append(_DIVIDER)
    lines.append("🎯 <b>Главное на сегодня</b>")
    lines.append(f"   {_esc(main_task.title)}")
    if main_task.due_date:
        lines.append(f"   <i>{format_due_human(main_task.due_date)}</i>")

    rest = [t for t in (today_tasks + upcoming) if t is not main_task]
    if rest:
        lines.append("")
        lines.append("📋 <b>Дальше</b>")
        lines.extend(_format_task_line(t) for t in rest)

    overdue_display = [t for t in overdue if t is not main_task]
    if overdue_display:
        lines.append("")
        lines.append(f"⚠️ <b>Просрочено ({len(overdue_display)})</b>")
        lines.extend(
            _format_task_line(t, in_overdue_section=True) for t in overdue_display
        )

    return "\n".join(lines)


async def _format_habits_section(
    telegram_user_id: int, habits: list[Habit], habit_service: HabitService
) -> str:
    if not habits:
        return ""

    streaks = await habit_service.get_streaks_bulk(
        telegram_user_id, [h.id for h in habits]
    )
    lines = ["", "🔁 <b>Привычки</b>"]
    for habit in habits:
        streak = streaks.get(habit.id, 0)
        suffix = f" 🔥 {streak}" if streak > 0 else ""
        lines.append(f"   {_esc(habit.title)}{suffix}")
    return "\n".join(lines)


def _progress_bar(percent: int, width: int = 10) -> str:
    filled = round(max(0, min(100, percent)) / 100 * width)
    return "▓" * filled + "░" * (width - filled)


def _format_goals_and_projects_section(
    goals: list[Goal], projects: list[MemoryEntry]
) -> str:
    """Цели — из Goals Service (со структурированным прогрессом), проекты —
    из Memory (отдельного Projects Service нет), см. specs/005-goals.md."""
    if not goals and not projects:
        return ""

    lines = [""]
    if goals:
        lines.append("🎯 <b>Цели</b>")
        lines.extend(
            f"   {_esc(goal.title)}  {_progress_bar(goal.progress)} {goal.progress}%"
            for goal in goals[:_MAX_MEMORY_ITEMS]
        )
    if projects:
        lines.append("")
        lines.append("📁 <b>Проекты</b>")
        lines.extend(
            f"   {_esc(entry.content)}" for entry in projects[:_MAX_MEMORY_ITEMS]
        )
    return "\n".join(lines)


async def _generate_insight(ai_client: AIClient, briefing_text: str) -> str | None:
    """Одна короткая AI-фраза по уже собранному брифингу, либо None при сбое."""
    messages = [
        {"role": "system", "content": _INSIGHT_SYSTEM_PROMPT},
        {"role": "user", "content": briefing_text},
    ]
    try:
        insight = await ai_client.complete(messages)
    except AIServiceError as exc:
        logger.warning("AI-инсайт для брифинга не сгенерирован: %s", exc)
        return None

    insight = insight.strip()
    return insight or None


async def build_morning_briefing(
    telegram_user_id: int,
    task_service: TaskService,
    memory_service: MemoryService,
    habit_service: HabitService,
    goal_service: GoalService,
    ai_client: AIClient | None = None,
) -> str:
    tasks = await task_service.list_active_tasks(telegram_user_id)
    habits = await habit_service.list_active_habits(telegram_user_id)
    goals = await goal_service.list_active_goals(telegram_user_id)
    projects = await memory_service.list_entries(
        telegram_user_id, type=MemoryType.PROJECT
    )

    parts = [_format_tasks_section(tasks, date.today())]

    habits_section = await _format_habits_section(
        telegram_user_id, habits, habit_service
    )
    if habits_section:
        parts.append(habits_section)

    goals_section = _format_goals_and_projects_section(goals, projects)
    if goals_section:
        parts.append(goals_section)

    text = "\n".join(parts)

    if ai_client is not None:
        insight = await _generate_insight(ai_client, text)
        if insight:
            text = f"{text}\n\n{_DIVIDER}\n💡 <i>{_esc(insight)}</i>"

    return text
