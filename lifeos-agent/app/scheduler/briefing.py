"""
Сборка текста утреннего брифинга (см. flows/001-morning-briefing.md).

Без AI: собирает Tasks + Memory в шаблонный текст. Когда появится
AI Service — эта функция заменится на вызов AI с тем же собранным
контекстом, вызывающий код (app/telegram/jobs.py) не изменится.
"""

from datetime import date

from app.goals.models import Goal
from app.goals.service import GoalService
from app.habits.models import Habit
from app.habits.service import HabitService
from app.memory.models import MemoryEntry, MemoryType
from app.memory.service import MemoryService
from app.tasks.models import Task
from app.tasks.service import TaskService

_MAX_MEMORY_ITEMS = 3


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


def _format_task_line(task: Task) -> str:
    suffix = f" — {task.due_date:%d.%m.%Y}" if task.due_date else ""
    return f"• {task.title}{suffix}"


def _format_tasks_section(tasks: list[Task]) -> str:
    lines = ["Доброе утро! ☀️"]

    overdue, today_tasks, upcoming = _split_tasks(tasks, date.today())
    main_task = _pick_main_task(overdue, today_tasks, upcoming)

    if main_task is None:
        lines.append("")
        lines.append("На сегодня активных задач нет.")
        return "\n".join(lines)

    lines.append("")
    lines.append(f"Главная задача дня: «{main_task.title}»")

    rest = [t for t in (today_tasks + upcoming) if t is not main_task]
    if rest:
        lines.append("")
        lines.append("Остальные задачи:")
        lines.extend(_format_task_line(t) for t in rest)

    overdue_display = [t for t in overdue if t is not main_task]
    if overdue_display:
        lines.append("")
        lines.append("⚠️ Просрочено:")
        lines.extend(_format_task_line(t) for t in overdue_display)

    return "\n".join(lines)


async def _format_habits_section(
    habits: list[Habit], habit_service: HabitService
) -> str:
    if not habits:
        return ""

    lines = ["", "Привычки на сегодня:"]
    for habit in habits:
        streak = await habit_service.get_streak(habit.id)
        suffix = f" — 🔥 {streak}" if streak > 0 else ""
        lines.append(f"• {habit.title}{suffix}")
    return "\n".join(lines)


def _format_goals_and_projects_section(
    goals: list[Goal], projects: list[MemoryEntry]
) -> str:
    """Цели — из Goals Service (со структурированным прогрессом), проекты —
    из Memory (отдельного Projects Service нет), см. specs/005-goals.md."""
    if not goals and not projects:
        return ""

    lines = ["", "Не забывайте:"]
    lines.extend(
        f"🎯 {goal.title} — {goal.progress}%" for goal in goals[:_MAX_MEMORY_ITEMS]
    )
    lines.extend(f"📁 {entry.content}" for entry in projects[:_MAX_MEMORY_ITEMS])
    return "\n".join(lines)


async def build_morning_briefing(
    telegram_user_id: int,
    task_service: TaskService,
    memory_service: MemoryService,
    habit_service: HabitService,
    goal_service: GoalService,
) -> str:
    tasks = await task_service.list_active_tasks(telegram_user_id)
    habits = await habit_service.list_active_habits(telegram_user_id)
    goals = await goal_service.list_active_goals(telegram_user_id)
    projects = await memory_service.list_entries(
        telegram_user_id, type=MemoryType.PROJECT
    )

    parts = [_format_tasks_section(tasks)]

    habits_section = await _format_habits_section(habits, habit_service)
    if habits_section:
        parts.append(habits_section)

    goals_section = _format_goals_and_projects_section(goals, projects)
    if goals_section:
        parts.append(goals_section)

    return "\n".join(parts)
