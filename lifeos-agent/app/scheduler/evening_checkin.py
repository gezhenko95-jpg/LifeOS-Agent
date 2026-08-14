"""
Итоги дня для вечернего слота 19:00 (см. flows/009-daily-rhythm.md) —
что сделано сегодня по задачам и привычкам. Отдельно от глубокого
дневникового вопроса 21:00 (app/scheduler/evening_reflection.py).

Оформление — HTML, как у утреннего брифинга (см. app/scheduler/briefing.py).
"""

from datetime import date, datetime, time, timezone

from app.habits.service import HabitService
from app.scheduler.briefing import format_today
from app.tasks.service import TaskService

_DIVIDER = "━━━━━━━━━━━━━━━"


def _progress_bar(done: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return ""
    filled = round(done / total * width)
    return "▓" * filled + "░" * (width - filled)


def _closing_line(completed: int, habits_done: int, habits_total: int) -> str:
    """Одна фраза-реакция вместо сухих цифр.

    Ноль задач — не повод для укора: день мог быть занят чем-то, чего в
    боте нет. Тон подбирается по факту, но без осуждения — иначе вечерние
    итоги хочется закрыть не читая.
    """
    if completed == 0 and habits_done == 0:
        return "Сегодня без отметок — бывает. Завтра новый заход. 🌱"
    if habits_total and habits_done == habits_total:
        return "Все привычки закрыты — отличный день. 🔥"
    if completed >= 3:
        return "Продуктивно получилось. 👏"
    return "Понемногу, но движение есть. 🙂"


async def build_evening_checkin_text(
    telegram_user_id: int, task_service: TaskService, habit_service: HabitService
) -> str:
    local_tz = datetime.now().astimezone().tzinfo
    today_start = datetime.combine(date.today(), time.min, tzinfo=local_tz).astimezone(
        timezone.utc
    )
    now = datetime.now(timezone.utc)
    completed_today = await task_service.count_tasks_completed_between(
        telegram_user_id, today_start, now
    )

    habits = await habit_service.list_active_habits(telegram_user_id)
    done_today = 0
    for habit in habits:
        completed_days = await habit_service.get_completed_days(habit.id, date.today())
        if date.today() in completed_days:
            done_today += 1

    lines = [
        "🌙 <b>Итоги дня</b>",
        f"<i>{format_today(date.today())}</i>",
        "",
        _DIVIDER,
        f"✅ Задач выполнено: <b>{completed_today}</b>",
    ]
    if habits:
        bar = _progress_bar(done_today, len(habits))
        lines.append(f"🔁 Привычек отмечено: <b>{done_today}/{len(habits)}</b>  {bar}")
    lines.append("")
    lines.append(_closing_line(completed_today, done_today, len(habits)))
    return "\n".join(lines)
